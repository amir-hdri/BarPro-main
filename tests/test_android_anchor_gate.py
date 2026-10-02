"""Tests for the Android anchor verification and its gate in the shipping pipeline.

verify_android_anchor() is the fail-closed read-back check: the auto-complete
flow must NOT proceed when the Android device's actual location does not match
the expected destination anchor. Previously this path had no test coverage.
"""

import contextlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models_multitenant import Client, Driver, WaybillJob
from app.services.shipping_travel_service import verify_android_anchor
from app.travel.providers import AndroidLocationObservation

# Tehran-ish anchor used across these tests.
ANCHOR_LAT = 35.6892
ANCHOR_LNG = 51.3890


def _observation(lat: float, lng: float) -> AndroidLocationObservation:
    now = datetime.now(UTC)
    return AndroidLocationObservation(
        latitude=lat,
        longitude=lng,
        serial="test-serial",
        provider="gps",
        is_mock=True,
        sampled_at=now,
        observed_at=now,
    )


def _observer_with(lat: float, lng: float):
    observer = MagicMock()
    observer.observe = AsyncMock(return_value=_observation(lat, lng))
    return observer


@pytest.mark.asyncio
async def test_verify_anchor_within_tolerance():
    """A read-back ~1 m from the anchor verifies."""
    with patch(
        "app.travel.android_observer.AdbLocationObserver",
        return_value=_observer_with(ANCHOR_LAT + 0.000005, ANCHOR_LNG),
    ):
        result = await verify_android_anchor(expected_lat=ANCHOR_LAT, expected_lng=ANCHOR_LNG)
    assert result["verified"] is True
    assert result["observation"]["is_mock"] is True
    assert result["observation"]["gap_m"] < 5.0


@pytest.mark.asyncio
async def test_verify_anchor_mismatch_beyond_tolerance():
    """A read-back kilometers away fails with a measured gap."""
    with patch(
        "app.travel.android_observer.AdbLocationObserver",
        return_value=_observer_with(35.0, 51.0),  # ~80 km away
    ):
        result = await verify_android_anchor(expected_lat=ANCHOR_LAT, expected_lng=ANCHOR_LNG)
    assert result["verified"] is False
    assert result["reason"] == "location_readback_mismatch"
    assert result["gap_m"] > 1000.0


@pytest.mark.asyncio
async def test_verify_anchor_fail_closed_on_observer_error():
    """Any observer failure fails closed — never verified."""
    observer = MagicMock()
    observer.observe = AsyncMock(side_effect=RuntimeError("adb unreachable"))
    with patch("app.travel.android_observer.AdbLocationObserver", return_value=observer):
        result = await verify_android_anchor(expected_lat=ANCHOR_LAT, expected_lng=ANCHOR_LNG)
    assert result["verified"] is False
    assert "reason" in result


# ── Pipeline gate: auto_complete_shipping must honor the anchor check ─────────


@pytest.fixture
async def async_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session = AsyncSession(engine, expire_on_commit=False)
    session.add(
        Client(
            id=1,
            client_code="c1",
            name="C",
            username="c1",
            full_name="C",
            email="c@c.c",
            hashed_password="x",
        )
    )
    session.add(
        Driver(
            id=1,
            client_id=1,
            driver_national_code="1",
            full_name="D",
            utcms_username="u",
            utcms_password_encrypted="enc",
            encrypted_password="x",
        )
    )
    session.add(
        WaybillJob(
            job_id="ship_job_1",
            idempotency_key="idem_ship_1",
            client_id=1,
            driver_id=1,
            # The authoritative flow verifies document ownership: state.doc_id must
            # appear in _document_ids(job) (the job.document_id column + payload/result
            # keys). Seed it so the gate under test (anchor verification) is reached.
            document_id="DOC-1",
            payload_json={},
            status="claimed",
            mutation_status="dispatched",
        )
    )
    await session.commit()
    yield session
    await session.close()
    await engine.dispose()


class _SessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _in_transit_state():
    from app.automation.gps_shipping_manager import ShippingState

    return ShippingState(
        job_id="ship_job_1",
        doc_id="DOC-1",
        status="in_transit",
        dest_lat=ANCHOR_LAT,
        dest_lng=ANCHOR_LNG,
        travel_status="enroute",
        # A real in_transit trip already past its physical ETA, so
        # shipping_wait_reason() passes and the flow reaches the anchor gate
        # instead of returning waiting_eta / invalid_estimated_end_at.
        estimated_end_at="2020-01-01T00:00:00+00:00",
    )


def _pipeline_patches(session, anchor_result):
    """Isolate every I/O seam the bridge-enabled auto-complete flow touches before
    the login step, so the test exercises ONLY the anchor gate.

    The production flow (authoritative, unchanged) acquires a Redis SET-NX
    completion claim, enforces ALLOW_LIVE_SUBMIT + the physical ETA, verifies
    document ownership, mocks the device location via FakeTraveler and reads it
    back. None of that is the gate under test, so each seam is stubbed to its
    success value — the same isolation pattern as test_shipping_gps_runtime.py.
    """
    bridge_config = MagicMock()
    bridge_config.enabled = True
    return [
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch(
            "app.automation.gps_shipping_manager._acquire_completion_claim",
            new_callable=AsyncMock,
            return_value="claim-token",
        ),
        patch(
            "app.automation.gps_shipping_manager._release_completion_claim",
            new_callable=AsyncMock,
        ),
        patch(
            "app.automation.gps_shipping_manager.load_shipping_state",
            new_callable=AsyncMock,
            return_value=_in_transit_state(),
        ),
        patch("app.automation.gps_shipping_manager.save_shipping_state", new_callable=AsyncMock),
        patch("app.core.database.async_session_factory", return_value=_SessionCM(session)),
        patch("app.android_bridge.client.BridgeConfig.from_env", return_value=bridge_config),
        patch(
            "app.android_bridge.controller.AndroidShippingController.apply_location",
            new_callable=AsyncMock,
        ),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://squid:3128"),
        patch(
            "app.services.shipping_travel_service.verify_android_anchor",
            new_callable=AsyncMock,
            return_value=anchor_result,
        ),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="secret"),
    ]


@pytest.mark.asyncio
async def test_auto_complete_blocked_when_anchor_not_verified(async_db: AsyncSession):
    """Bridge enabled + anchor mismatch → waiting_readback, no submission attempted."""
    from app.automation import gps_shipping_manager

    patches = _pipeline_patches(
        async_db,
        {"verified": False, "reason": "location_readback_mismatch", "gap_m": 80000.0},
    )
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        mock_login = stack.enter_context(
            patch.object(gps_shipping_manager, "get_or_login_client", new_callable=AsyncMock)
        )
        result = await gps_shipping_manager.auto_complete_shipping("ship_job_1")

    assert result["status"] == "waiting_readback"
    assert result["reason"] == "location_readback_mismatch"
    mock_login.assert_not_called()


@pytest.mark.asyncio
async def test_auto_complete_proceeds_when_anchor_verified(async_db: AsyncSession):
    """Bridge enabled + anchor verified → gate passes, flow reaches login step."""
    from app.automation import gps_shipping_manager

    sentinel = RuntimeError("sentinel-login-reached")
    patches = _pipeline_patches(async_db, {"verified": True, "observation": {}})
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch.object(
                gps_shipping_manager,
                "get_or_login_client",
                new_callable=AsyncMock,
                side_effect=sentinel,
            )
        )
        with pytest.raises(RuntimeError, match="sentinel-login-reached"):
            await gps_shipping_manager.auto_complete_shipping("ship_job_1")


@pytest.mark.asyncio
async def test_auto_complete_skips_gate_when_bridge_disabled(async_db: AsyncSession):
    """Bridge disabled → no anchor check, flow reaches login step."""
    from app.automation import gps_shipping_manager

    sentinel = RuntimeError("sentinel-login-reached")
    bridge_config = MagicMock()
    bridge_config.enabled = False
    with (
        patch("app.core.config.utcms_config.ALLOW_LIVE_SUBMIT", True),
        patch(
            "app.automation.gps_shipping_manager._acquire_completion_claim",
            new_callable=AsyncMock,
            return_value="claim-token",
        ),
        patch(
            "app.automation.gps_shipping_manager._release_completion_claim",
            new_callable=AsyncMock,
        ),
        patch(
            "app.automation.gps_shipping_manager.load_shipping_state",
            new_callable=AsyncMock,
            return_value=_in_transit_state(),
        ),
        patch("app.automation.gps_shipping_manager.save_shipping_state", new_callable=AsyncMock),
        patch("app.core.database.async_session_factory", return_value=_SessionCM(async_db)),
        patch("app.android_bridge.client.BridgeConfig.from_env", return_value=bridge_config),
        patch("app.automation.worker_proxy.get_worker_proxy_url", return_value="http://squid:3128"),
        patch("app.auth_multitenant.decrypt_driver_password", return_value="secret"),
        patch("app.services.shipping_travel_service.verify_android_anchor", new_callable=AsyncMock) as mock_verify,
        patch.object(gps_shipping_manager, "get_or_login_client", new_callable=AsyncMock, side_effect=sentinel),
    ):
        with pytest.raises(RuntimeError, match="sentinel-login-reached"):
            await gps_shipping_manager.auto_complete_shipping("ship_job_1")
    mock_verify.assert_not_called()
