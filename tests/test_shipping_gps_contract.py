"""Regression tests for server-managed shipping GPS semantics."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.shipping_gps import _assert_route_anchor, _document_ids
from app.automation.gps_shipping_manager import ShippingStatePersistenceError, init_shipping, save_shipping_state
from app.automation.http_browser_bridge import validate_submission_coordinates
from app.automation.location_selector import resolve_location_coordinates
from app.core.exceptions import WaybillError


def test_route_anchor_accepts_only_decimal_rounding() -> None:
    _assert_route_anchor(
        latitude=35.6892001,
        longitude=51.3890001,
        expected_lat=35.6892,
        expected_lng=51.389,
        label="مبدأ",
    )

    with pytest.raises(HTTPException) as exc_info:
        _assert_route_anchor(
            latitude=35.70,
            longitude=51.40,
            expected_lat=35.6892,
            expected_lng=51.389,
            label="مبدأ",
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_planned_waypoints_are_not_gps_evidence() -> None:
    state = await init_shipping(
        "job-1",
        "doc-1",
        {
            "originLat": 35.6892,
            "originLng": 51.389,
            "destLat": 32.6546,
            "destLng": 51.668,
            "originAddress": "مبدأ آزمون",
            "destAddress": "مقصد آزمون",
        },
        num_steps=3,
        persist=False,
    )
    assert len(state.waypoints) == 5
    assert state.gps_list == []
    assert all(point["type"] in {1, 2, 3} for point in state.waypoints)


def test_shipping_routes_use_session_vault_not_raw_login() -> None:
    """Verify shipping_gps.py imports get_or_login_client, NOT raw login helpers.

    Gap 1 fix: the routes must use the Redis Session Vault (get_or_login_client)
    instead of calling auto_solve_captcha + login directly, to prevent CAPTCHA
    spam and HTTP 429 from UTCMS.
    """
    import inspect

    from app.api.routes import shipping_gps

    source = inspect.getsource(shipping_gps)

    # Must use Session Vault
    assert "get_or_login_client" in source, "shipping_gps.py must import and use get_or_login_client for UTCMS auth"

    # Must NOT contain raw login patterns inside endpoint functions
    # (The `auto_solve_captcha` and `client.login(` patterns should NOT appear
    # as direct calls in the route handlers — they belong inside get_or_login_client)
    start_fn_src = inspect.getsource(shipping_gps.start_shipping)
    finish_fn_src = inspect.getsource(shipping_gps.finish_shipping)

    assert (
        "auto_solve_captcha" not in start_fn_src
    ), "/start must not call auto_solve_captcha directly (use get_or_login_client)"
    assert (
        "auto_solve_captcha" not in finish_fn_src
    ), "/finish must not call auto_solve_captcha directly (use get_or_login_client)"
    assert "client.login(" not in start_fn_src, "/start must not call client.login directly (use get_or_login_client)"
    assert "client.login(" not in finish_fn_src, "/finish must not call client.login directly (use get_or_login_client)"


def test_shipping_routes_import_proxy_unavailable_error() -> None:
    """Verify shipping_gps.py catches ProxyUnavailableError separately.

    Gap 3 fix: proxy failures must return HTTP 503 (service unavailable),
    not 502 (bad gateway), and must never silently proceed without a proxy.
    """
    import inspect

    from app.api.routes import shipping_gps

    source = inspect.getsource(shipping_gps)

    assert "ProxyUnavailableError" in source, "shipping_gps.py must import and handle ProxyUnavailableError"

    start_fn_src = inspect.getsource(shipping_gps.start_shipping)
    finish_fn_src = inspect.getsource(shipping_gps.finish_shipping)

    assert "ProxyUnavailableError" in start_fn_src, "/start must catch ProxyUnavailableError for HTTP 503"
    assert "ProxyUnavailableError" in finish_fn_src, "/finish must catch ProxyUnavailableError for HTTP 503"
    assert "status_code=503" in start_fn_src, "/start must return 503 for proxy failures, not 502"
    assert "status_code=503" in finish_fn_src, "/finish must return 503 for proxy failures, not 502"


def test_shipping_routes_fail_closed_guard_when_proxy_none() -> None:
    """Verify shipping_gps.py guards against proxy_url is None in production.

    Defensive guard: even if get_worker_proxy_url() returned None (e.g. if
    someone improperly set PROXY_FAIL_CLOSED=false), the route handlers must
    actively check and raise ProxyUnavailableError before attempting direct egress.
    """
    import inspect

    from app.api.routes import shipping_gps

    start_fn_src = inspect.getsource(shipping_gps.start_shipping)
    finish_fn_src = inspect.getsource(shipping_gps.finish_shipping)

    assert "proxy_url is None" in start_fn_src, "/start must explicitly guard against proxy_url is None in production"
    assert "proxy_url is None" in finish_fn_src, "/finish must explicitly guard against proxy_url is None in production"
    assert "force_reauth=True" in start_fn_src
    assert "force_reauth=True" in finish_fn_src


def test_location_coordinates_never_fall_back_to_tehran_for_unknown_city() -> None:
    assert resolve_location_coordinates({"city": "شهر ناشناخته"}) is None
    assert resolve_location_coordinates({"city": "کرج"}) == (35.8327, 50.9915)


def test_location_coordinates_prefer_explicit_coordinates() -> None:
    assert resolve_location_coordinates({"city": "کرج", "coordinates": {"lat": 35.84, "lng": 50.94}}) == (35.84, 50.94)


def test_submission_bridge_rejects_missing_coordinates_instead_of_inventing_them() -> None:
    with pytest.raises(WaybillError, match="مختصات واقعی"):
        validate_submission_coordinates("sourceLatM=&sourceLonM=&destLatM=&destLonM=")

    validate_submission_coordinates("sourceLatM=35.6892&sourceLonM=51.389&destLatM=32.65&destLonM=51.66")


def test_document_ids_are_extracted_from_job_and_result_without_accepting_ambiguity() -> None:
    job = SimpleNamespace(document_id="doc-123", result_json={"document_id": "doc-123"})
    assert _document_ids(job, {"docNo": "doc-123"}) == {"doc-123"}


@pytest.mark.asyncio
async def test_shipping_state_does_not_fail_open_when_both_stores_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.automation.gps_shipping_manager._get_redis",
        lambda: __import__("asyncio").sleep(0, result=None),
    )
    monkeypatch.setattr(
        "app.automation.gps_shipping_manager._persist_shipping_state_db",
        lambda state: __import__("asyncio").sleep(0, result=False),
    )
    with pytest.raises(ShippingStatePersistenceError):
        await save_shipping_state(SimpleNamespace(job_id="job", to_dict=lambda: {"job_id": "job"}))
