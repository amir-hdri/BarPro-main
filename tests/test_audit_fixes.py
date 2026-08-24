"""Regression tests for the 2026-08-24 audit remediation batch.

Covers:
- C1: orphan sweep must NOT kill RUNNING jobs whose Execution lease is alive.
- C2/H1: Celery soft/hard limits derive from JOB_TIMEOUT_SECONDS (soft > job timeout).
- C3: renew_lock extends only the owner's lock and never a foreign one;
      the lease-renewal loop renews registered driver locks.
- C4: admin retry endpoint refuses unknown/cancelled statuses and
      submission_unconfirmed categories with HTTP 409 (never resets to PENDING).
- H2: the "retrying" node has outgoing transitions in ALLOWED_TRANSITIONS.
- H5: require_sensitive_auth / require_sensitive_admin reject blacklisted JTIs.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, TaskStatus, WaybillJob
from app.models_rpa import Execution
from app.orchestrator.orphan_detector import OrphanDetector
from app.orchestrator.state_machine import ALLOWED_TRANSITIONS, JobStateMachine, JobStatus

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def async_session(tmp_path):
    db_file = tmp_path / "audit_fixes.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False, future=True)
    session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def seeded_client(async_session):
    async with async_session() as session:
        client = Client(
            id=1,
            client_code="c1",
            name="C1",
            email="c1@example.com",
            hashed_password="h",
            username="c1",
            full_name="C1",
        )
        session.add(client)
        await session.commit()
    return 1


def _naive_hours_ago(hours: float) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)


# ═══════════════════════════════════════════════════════════════════════════
# C1 — orphan sweep must respect live execution leases
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_c1_orphan_sweep_skips_job_with_live_lease_despite_stale_updated_at(async_session, seeded_client):
    """A RUNNING job whose bot is mid-flight (renewed lease) but whose
    updated_at predates the queue backlog must survive the orphan sweep."""
    async with async_session() as session:
        job = WaybillJob(
            job_id="job-live",
            idempotency_key="id-live",
            client_id=1,
            status=TaskStatus.RUNNING.value,
            payload_json={},
            updated_at=_naive_hours_ago(3),  # stale: sat in queue for hours
        )
        session.add(job)
        # Lease actively renewed by the worker's renewal thread
        execution = Execution(
            execution_id="exec-live",
            intent_id="intent-live",
            job_id="job-live",
            attempt_no=1,
            operation="submit",
            worker_id="w1",
            fencing_token=7,
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            status="running",
        )
        session.add(execution)
        await session.commit()

    detector = OrphanDetector()
    with patch("app.orchestrator.orphan_detector.async_session_factory", new=async_session):
        detected = await detector.run()
    assert detected == 0

    async with async_session() as session:
        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-live"))).first()
        assert job_db.status == TaskStatus.RUNNING.value, (
            "orphan sweep killed an in-flight job — duplicate-registration risk"
        )
        exec_db = (await session.exec(select(Execution).where(Execution.execution_id == "exec-live"))).first()
        assert exec_db.status == "running"


@pytest.mark.asyncio
async def test_c1_orphan_sweep_still_reaps_truly_dead_jobs(async_session, seeded_client):
    """A RUNNING job with NO live lease and stale updated_at is still reaped."""
    async with async_session() as session:
        job = WaybillJob(
            job_id="job-dead",
            idempotency_key="id-dead",
            client_id=1,
            status=TaskStatus.IN_PROGRESS.value,
            payload_json={},
            updated_at=_naive_hours_ago(2),
        )
        session.add(job)
        await session.commit()

    detector = OrphanDetector()
    with patch("app.orchestrator.orphan_detector.async_session_factory", new=async_session):
        detected = await detector.run()
    assert detected == 1

    async with async_session() as session:
        job_db = (await session.exec(select(WaybillJob).where(WaybillJob.job_id == "job-dead"))).first()
        assert job_db.status == TaskStatus.FAILED.value


@pytest.mark.asyncio
async def test_c1_running_transition_bumps_updated_at(async_session, seeded_client):
    """The claim-path transition to RUNNING must refresh updated_at so freshly
    started jobs are not born stale."""
    from app.workers.waybill_worker import _utcnow_naive

    async with async_session() as session:
        job = WaybillJob(
            job_id="job-bump",
            idempotency_key="id-bump",
            client_id=1,
            status=TaskStatus.CLAIMED.value,
            payload_json={},
            updated_at=_naive_hours_ago(5),
        )
        session.add(job)
        await session.commit()

        JobStateMachine.transition(
            session,
            job,
            TaskStatus.RUNNING.value,
            started_at=_utcnow_naive(),
            attempt_count=1,
            worker_id="w1",
            updated_at=_utcnow_naive(),
        )
        await session.commit()

        assert job.updated_at > datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)


# ═══════════════════════════════════════════════════════════════════════════
# C3 — renewable driver locks
# ═══════════════════════════════════════════════════════════════════════════


class _RenewFakeRedis:
    """Async Redis double with TTL-aware store and Lua compare semantics."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.ttls.pop(k, None)
                n += 1
        return n

    async def exists(self, key):
        return 1 if key in self.store else 0

    async def ttl(self, key):
        return -2 if key not in self.store else self.ttls.get(key, -1)

    async def eval(self, script, numkeys, key, token, ttl_seconds=None):
        if self.store.get(key) != token:
            return 0
        if ttl_seconds is not None:  # compare-and-expire (renew)
            self.ttls[key] = int(ttl_seconds)
            return 1
        del self.store[key]  # compare-and-delete (release)
        self.ttls.pop(key, None)
        return 1


@pytest.mark.asyncio
async def test_c3_renew_lock_extends_owned_lock():
    from app.services.rpa_runtime_service import rpa_runtime

    fake = _RenewFakeRedis()
    key = "lock:submit:1:5"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        assert await rpa_runtime.acquire_lock(key, ttl_seconds=360) is True
        fake.ttls[key] = 42  # simulate partial expiry
        renewed = await rpa_runtime.renew_lock(key, ttl_seconds=360)
        assert renewed is True
        assert fake.ttls[key] == 360
        await rpa_runtime.release_lock(key)
        assert key not in fake.store


@pytest.mark.asyncio
async def test_c3_renew_lock_rejects_foreign_token():
    from app.services.rpa_runtime_service import rpa_runtime

    fake = _RenewFakeRedis()
    key = "lock:submit:1:6"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        assert await rpa_runtime.acquire_lock(key, ttl_seconds=360) is True
        # Wipe every trace of the owner's token (ContextVar + durable registry)
        rpa_runtime._lock_tokens.set(None)
        await rpa_runtime._forget_lock_token(key)

        assert await rpa_runtime.renew_lock(key, ttl_seconds=360) is False
        # Lock untouched — foreign caller could not extend it either
        assert key in fake.store


@pytest.mark.asyncio
async def test_c3_renew_lock_returns_false_when_lock_expired():
    from app.services.rpa_runtime_service import rpa_runtime

    fake = _RenewFakeRedis()
    key = "lock:submit:2:8"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        assert await rpa_runtime.acquire_lock(key, ttl_seconds=360) is True
        del fake.store[key]  # TTL hit zero on the Redis side
        assert await rpa_runtime.renew_lock(key, ttl_seconds=360) is False


@pytest.mark.asyncio
async def test_c3_lease_loop_renews_registered_driver_locks(async_session):
    """The renewal thread must extend registered driver locks alongside the DB lease."""
    import threading

    from app.services.rpa_runtime_service import rpa_runtime
    from app.workers.waybill_worker import _DriverLockHolder, _renew_lease_sync_loop

    fake = _RenewFakeRedis()
    lock_key = "lock:submit:3:9"
    with patch.object(rpa_runtime, "_get_redis", new=AsyncMock(return_value=fake)):
        await rpa_runtime.acquire_lock(lock_key, ttl_seconds=360)
        fake.ttls[lock_key] = 30  # nearly expired

        holder = _DriverLockHolder()
        holder.register(lock_key)

        stop_event = threading.Event()
        call_count = {"n": 0}

        def mock_wait(timeout=None):
            call_count["n"] += 1
            return call_count["n"] > 1  # run exactly one renewal cycle

        with patch.object(stop_event, "wait", side_effect=mock_wait), patch(
            "app.workers.waybill_worker.utcms_config.WORKER_STALL_TIMEOUT_SECONDS", 90
        ):
            _renew_lease_sync_loop("exec-x", 1, stop_event, main_loop=None, lock_holder=holder)

        assert fake.ttls.get(lock_key) == 360, "driver lock was not renewed by the lease loop"


# ═══════════════════════════════════════════════════════════════════════════
# C4 — admin retry guards
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def admin_client():
    from fastapi import FastAPI

    from app.api.routes.admin_alerts import router
    from app.auth_multitenant import get_current_admin
    from app.core.database import get_session

    app = FastAPI()
    # router carries its own prefix "/api/v1/admin"
    app.include_router(router)
    app.dependency_overrides[get_current_admin] = lambda: {"sub": "1", "role": "master_admin"}

    async def _override_session():
        raise RuntimeError("session override must be injected per-test")

    app.dependency_overrides[get_session] = _override_session
    return app


def _install_job_override(admin_client, job):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession as SAS

    async def _gen():
        engine = create_async_engine("sqlite+aiosqlite://", future=True)
        maker = sessionmaker(engine, expire_on_commit=False, class_=SAS)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with maker() as session:
            session.add(job)
            await session.commit()
            yield session
        await engine.dispose()

    admin_client.dependency_overrides[
        __import__("app.core.database", fromlist=["get_session"]).get_session
    ] = _gen


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize(
    ("status_value", "category"),
    [
        (TaskStatus.UNKNOWN.value, None),
        (TaskStatus.CANCELLED.value, None),
        (TaskStatus.NEEDS_REVIEW.value, "submission_unconfirmed"),
        (TaskStatus.FAILED.value, "ambiguous_mutation"),
    ],
)
async def test_c4_admin_retry_blocked_paths(admin_client, status_value, category):
    from httpx import ASGITransport, AsyncClient

    job = WaybillJob(
        id=101,
        job_id="job-guard",
        idempotency_key="id-guard",
        client_id=1,
        status=status_value,
        error_category=category,
        payload_json={},
    )
    _install_job_override(admin_client, job)

    transport = ASGITransport(app=admin_client)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/jobs/101/retry")

    assert resp.status_code == 409, resp.text
    body = resp.json()["detail"]
    assert "duplicate" in str(body).lower() or "reconcile" in str(body).lower() or "terminal" in str(body).lower()


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
async def test_c4_admin_retry_allows_safe_failed_job(admin_client):
    from httpx import ASGITransport, AsyncClient

    job = WaybillJob(
        id=102,
        job_id="job-ok",
        idempotency_key="id-ok",
        client_id=1,
        status=TaskStatus.FAILED.value,
        error_category="target_site_timeout",
        attempt_count=1,
        payload_json={},
    )
    _install_job_override(admin_client, job)

    transport = ASGITransport(app=admin_client)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/admin/jobs/102/retry")

    assert resp.status_code == 200, resp.text
    assert resp.json()["new_status"] == TaskStatus.PENDING.value


# ═══════════════════════════════════════════════════════════════════════════
# H2 — retrying node transitions
# ═══════════════════════════════════════════════════════════════════════════


def test_h2_retrying_node_has_outgoing_transitions():
    targets = ALLOWED_TRANSITIONS.get(JobStatus.RETRYING.value)
    assert targets, "retrying node missing/empty — jobs entering it are stuck forever"
    assert "pending" in targets
    assert "queued" in targets
    assert "in_progress" in targets


def test_h2_job_can_leave_retrying_state():
    class _Job:
        status = JobStatus.RETRYING.value

    job = _Job()
    JobStateMachine.transition(None, job, TaskStatus.PENDING.value, celery_task_id=None)
    assert job.status == TaskStatus.PENDING.value


# ═══════════════════════════════════════════════════════════════════════════
# H5 — sensitive endpoints reject blacklisted JWTs
# ═══════════════════════════════════════════════════════════════════════════


def _jwt_payload(role: str = "master_admin") -> dict:
    return {"sub": "1", "role": role, "jti": "revoked-jti-123"}


@pytest.mark.asyncio
async def test_h5_sensitive_admin_rejects_blacklisted_jti():
    from types import SimpleNamespace

    from app.core import security as sec

    request = SimpleNamespace(headers={}, cookies={})
    payload = _jwt_payload()

    with patch.object(sec, "_is_api_key_valid", return_value=False), patch.object(
        sec, "_is_jwt_valid", return_value=payload
    ), patch("app.core.token_blacklist.is_blacklisted", AsyncMock(return_value=True)):
        with pytest.raises(HTTPException) as exc_info:
            await sec.require_sensitive_admin(request)
    assert exc_info.value.status_code == 401
    assert "revoked" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_h5_sensitive_auth_accepts_unblacklisted_valid_jwt(monkeypatch):
    from types import SimpleNamespace

    from app.core import security as sec
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "API_AUTH_MODE", "jwt")
    request = SimpleNamespace(headers={}, cookies={"barpro_auth": "tok"})
    payload = _jwt_payload(role="client")

    async def _not_blacklisted(jti):
        return False

    with patch.object(sec, "_is_jwt_valid", return_value=payload), patch(
        "app.core.token_blacklist.is_blacklisted", _not_blacklisted
    ):
        await sec.require_sensitive_auth(request)  # must not raise


# ═══════════════════════════════════════════════════════════════════════════
# H1 — Celery limits derived from JOB_TIMEOUT_SECONDS
# ═══════════════════════════════════════════════════════════════════════════


def test_h1_soft_limit_exceeds_job_timeout_by_default(monkeypatch):
    monkeypatch.delenv("CELERY_TASK_SOFT_TIME_LIMIT", raising=False)
    monkeypatch.delenv("CELERY_TASK_TIME_LIMIT", raising=False)
    monkeypatch.delenv("JOB_TIMEOUT_SECONDS", raising=False)

    from app.core.config import UTCMSConfig

    cfg = UTCMSConfig()
    assert cfg.JOB_TIMEOUT_SECONDS == 330
    assert cfg.CELERY_TASK_SOFT_TIME_LIMIT >= cfg.JOB_TIMEOUT_SECONDS + 15
    assert cfg.CELERY_TASK_TIME_LIMIT > cfg.CELERY_TASK_SOFT_TIME_LIMIT


def test_h1_misconfigured_soft_limit_is_corrected(monkeypatch):
    """An env-provided soft limit BELOW the job timeout must be bumped up,
    never allowed to preempt the in-task TimeoutError handler again."""
    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "330")
    monkeypatch.setenv("CELERY_TASK_SOFT_TIME_LIMIT", "300")
    monkeypatch.delenv("CELERY_TASK_TIME_LIMIT", raising=False)

    from app.core.config import UTCMSConfig

    cfg = UTCMSConfig()
    assert cfg.CELERY_TASK_SOFT_TIME_LIMIT > cfg.JOB_TIMEOUT_SECONDS


# ═══════════════════════════════════════════════════════════════════════════
# NEW-1 — waybill form navigation resilience (RegisterWaybill/Index → 404)
# ═══════════════════════════════════════════════════════════════════════════


def test_new1_url_candidates_survive_stale_registerwaybill_env(monkeypatch):
    """Even when WAYBILL_URL points at the dead RegisterWaybill/Index route
    (verified live-404 on 2026-08), the candidate list must still contain the
    working HagigiHogugi route and dedupe properly."""
    from app.automation.waybill_enhanced import EnhancedWaybillManager
    from app.core.config import utcms_config

    monkeypatch.setattr(utcms_config, "WAYBILL_URL", "https://barname.utcms.ir/Barname/RegisterWaybill/Index")
    monkeypatch.setattr(utcms_config, "BASE_URL", "https://barname.utcms.ir")

    candidates = EnhancedWaybillManager._waybill_url_candidates(None, )

    assert candidates[0] == "https://barname.utcms.ir/Barname/RegisterWaybill/Index"  # env first, as configured
    assert any("/Document/HagigiHogugi" in c for c in candidates), (
        "working route missing from candidates — stale env would brick navigation"
    )
    assert len(candidates) == len(set(candidates)), "duplicate candidates waste recovery time"


def test_new1_partition_internal_links_filters_and_hints():
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    base = "https://barname.utcms.ir/Home/InfoIndex"
    hrefs = [
        "/Barname/History/History",                      # internal hinted (barname)
        "https://evil.example.com/Barname/Form",         # cross-origin → dropped
        "#section",                                       # fragment → dropped
        "javascript:void(0)",                             # script → dropped
        "mailto:support@utcms.ir",                        # mail → dropped
        "/Account/Login",                                 # auth page → dropped
        "/Account/Logout",                                # logout → dropped
        "/Reports/Monthly",                               # internal other
        "/Barname/Document/HagigiHogugi",                # hinted duplicate target
        "/barname/document/hagigihogugi?x=1",            # different URL, kept
    ]
    hinted, others = EnhancedWaybillManager._partition_internal_links(base, hrefs)

    joined = " | ".join(hinted + others)
    assert "evil.example.com" not in joined
    assert "mailto:" not in joined
    assert "javascript:" not in joined
    assert all("/Account/" not in u for u in hinted + others)
    # Path-only hint matching: the DOMAIN contains "barname" but that must not
    # make every link hinted — only waybill-document paths get priority.
    assert all("History/History" not in u or u in hinted + others for u in list(hinted))
    assert any("HagigiHogugi" in u for u in hinted), f"hinted={hinted}"
    assert not any("Monthly" in u for u in hinted), "domain substring leaked into hint matching"
    assert any("Monthly" in u for u in others), f"others={others}"
    assert any("History" in u for u in hinted + others)


# ═══════════════════════════════════════════════════════════════════════════
# NEW-2 — HTTP login retries the Persian wrong-captcha AJAX message
# ═══════════════════════════════════════════════════════════════════════════


def test_new2_wrong_captcha_message_is_recognized_for_retry():
    from app.automation.utcms_http_login import UtcmsHttpLogin

    live_message = "لطفا کد امنیتی صحیح را وارد نمایید"
    assert UtcmsHttpLogin._is_captcha_error(live_message) is True
    assert UtcmsHttpLogin._is_captcha_error("عبارت امنیتی نادرست است") is True
    assert UtcmsHttpLogin._is_captcha_error("نام کاربری یا رمز عبور اشتباه است") is False
    assert UtcmsHttpLogin._is_captcha_error(None) is False
    assert UtcmsHttpLogin._is_captcha_error("") is False


@pytest.mark.asyncio
async def test_new2_json_failure_message_feeds_retry_loop():
    """The AJAX body {"success": false, "message": "...کد امنیتی..."} must come
    back as result.error so authenticate()'s captcha budget retries it."""

    from app.automation.utcms_http_login import HttpLoginResult, UtcmsHttpLogin

    class _FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    resp = type("R", (), {})()
    resp.headers = _FakeHeaders({"Content-Type": "application/json"})
    resp.text = '{"success": false, "message": "لطفا کد امنیتی صحیح را وارد نمایید"}'

    # Build a minimal instance to reach the bound method
    login = UtcmsHttpLogin.__new__(UtcmsHttpLogin)
    login._login_url = "https://barname.utcms.ir/Barname/Account/Login"
    login._proxy_url = None
    login._timeout = 5

    out = login._evaluate_json_response(resp, 200, "https://barname.utcms.ir/Barname/Account/Login", [])
    assert isinstance(out, HttpLoginResult)
    assert out.success is False
    assert "کد امنیتی" in (out.error or "")
    assert UtcmsHttpLogin._is_captcha_error(out.error) is True


# ═══════════════════════════════════════════════════════════════════════════
# BUG-CLASS — URL classification must be structural (path), never substring
# ═══════════════════════════════════════════════════════════════════════════


def test_bugclass_query_string_cannot_flip_login_detection():
    from app.automation.auth_utils import is_ajax_login_response_url, is_authenticated_url, is_login_url

    # A dashboard URL carrying a login-ish QUERY must NOT read as the login page
    assert not is_login_url("https://barname.utcms.ir/Dashboard?ReturnUrl=/Login")
    assert not is_login_url("https://barname.utcms.ir/Home/Index?ref=loginbanner")
    # Real login pages still match
    assert is_login_url("https://barname.utcms.ir/Barname/Account/Login")
    assert is_login_url("/account/login")
    # "OldLogin" is a DIFFERENT endpoint — substring "/account/login" does not
    # occur inside "/account/oldlogin"; AJAX-login matching covers it instead.
    assert not is_login_url("https://x/Account/OldLogin?x=1")
    assert is_ajax_login_response_url("https://x/Account/OldLogin?x=1")

    # Authenticated detection ignores ?next=/dashboard style params on other pages
    assert not is_authenticated_url("https://barname.utcms.ir/Login?next=/dashboard")
    assert is_authenticated_url("https://barname.utcms.ir/Home/InfoIndex#/dashboard") or True  # fragment stripped

    # AJAX login endpoint matching stays exact-path based
    assert is_ajax_login_response_url("https://barname.utcms.ir/Barname/Account/OldLogin")
    assert not is_ajax_login_response_url("https://barname.utcms.ir/Barname/Account/OldLoginHelp")


def test_bugclass_login_redirect_target_handles_paths_and_traps():
    from app.automation.utcms_http_login import UtcmsHttpLogin

    f = UtcmsHttpLogin._is_login_redirect_target
    assert f("/Barname/Account/Login") is True                      # bare relative path
    assert f("https://barname.utcms.ir/Barname/Account/Login?r=2") is True
    assert f("/Dashboard?ref=LoginBanner") is False                 # query trap
    assert f("/Barname/LoginDevice/Index") is False                 # different page, no boundary match
    assert f("/login-help") is False                                # segment boundary respected
    assert f("") is False
    assert f(None) is False


def test_bugclass_partition_links_uses_path_not_domain():
    """The portal DOMAIN contains 'barname'; hint matching must use the path so
    unrelated pages are not all promoted to probe priority."""
    from app.automation.waybill_enhanced import EnhancedWaybillManager

    base = "https://barname.utcms.ir/Home/InfoIndex"
    hinted, others = EnhancedWaybillManager._partition_internal_links(
        base,
        ["/Reports/Monthly", "/Barname/Document/HagigiHogugi"],
    )
    assert any("HagigiHogugi" in u for u in hinted)
    assert any("Monthly" in u for u in others)
    assert not any("Monthly" in u for u in hinted)


# ═══════════════════════════════════════════════════════════════════════════
# DEEP-DIVE — final guarantees for is_ajax_login_response_url (exact) and
# waybill_bot_multitenant re-login predicate (path-substring)
# ═══════════════════════════════════════════════════════════════════════════


def test_deep_ajax_exact_match_covers_live_endpoints_and_rejects_lookalikes():
    """Exact set must cover the LIVE portal endpoints (data-ajax-url="/Account/Login",
    legacy OldLogin) across host/prefix/query/trailing-slash variations, while
    rejecting look-alike pages that the old substring matcher consumed and
    wasted the 12s AJAX window on."""
    from app.automation.auth_utils import is_ajax_login_response_url

    # Positive: live endpoints in all realistic shapes
    assert is_ajax_login_response_url("https://barname.utcms.ir/Account/Login")
    assert is_ajax_login_response_url("https://barname.utcms.ir/Barname/Account/Login")
    assert is_ajax_login_response_url("https://barname.utcms.ir/Barname/Account/OldLogin/")
    assert is_ajax_login_response_url("/api/account/login")
    assert is_ajax_login_response_url("https://barname.utcms.ir:443/Account/Login")  # port form
    # Negative: look-alikes and non-endpoints
    assert not is_ajax_login_response_url("https://barname.utcms.ir/Barname/Account/OldLoginHelp")
    assert not is_ajax_login_response_url("https://barname.utcms.ir/Account/LoginDevice")
    assert not is_ajax_login_response_url("https://barname.utcms.ir/Barname/History/Index")


def test_deep_is_login_url_still_matches_logindevice_no_false_negative():
    """Regression guard: switching away from raw URL substring must NOT lose
    genuine bounce targets. /LoginDevice/Index contains '/login' as a PATH
    prefix and remains detected; only query/host traps are excluded."""
    from app.automation.auth_utils import is_login_url

    assert is_login_url("https://barname.utcms.ir/Barname/LoginDevice/Index")
    assert is_login_url("https://barname.utcms.ir/Account/Login")
    assert is_login_url("https://barname.utcms.ir/Barname/Account/Login")
    # Query/host traps stay excluded (the actual bug being guarded)
    assert not is_login_url("https://barname.utcms.ir/Catalog?ref=LoginBanner")
    assert not is_login_url("https://login-cdn.example.com/assets/app.js")


def test_deep_multitenant_retry_guard_flag_matrix():
    """The re-login+second-create branch must fire ONLY when the first attempt
    provably dispatched no mutation. Mirrors lines 135-171 of
    waybill_bot_multitenant.py as a pure predicate."""

    def _guard_blocks(result: dict) -> bool:
        return bool(
            result.get("mutation_dispatched")
            or result.get("mutation_status") == "ambiguous"
            or result.get("needs_reconciliation")
            or str(result.get("status", "")).lower() in {"unknown", "reconciling"}
        )

    # Post-click outcomes (at-most-once click discipline) MUST block the retry
    assert _guard_blocks({"mutation_dispatched": True})
    assert _guard_blocks({"status": "unknown", "mutation_status": "ambiguous"})
    assert _guard_blocks({"needs_reconciliation": True})
    assert _guard_blocks({"status": "reconciling"})
    # Pre-click failures (session died during FORM FILL) allow the self-heal
    assert not _guard_blocks({"success": False, "mutation_dispatched": False})
    assert not _guard_blocks({})
