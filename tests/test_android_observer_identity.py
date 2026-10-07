"""Mock-provider evidence must belong to the particular observed fix."""

import pytest

from app.travel.android_observer import AdbLocationObserver, _parse_uptime_seconds

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("marker", ["mock=false", "isMock=false", "mock=0"])
def test_explicit_nonmock_fix_cannot_borrow_positive_marker(marker: str) -> None:
    dump = f"Location[gps 35.7,51.4 {marker} age=0.0s]\n" "  gps provider:\n" "    Mocked by cl.coders.faketraveler\n"
    parsed = AdbLocationObserver.parse_dump(dump)
    assert parsed is not None
    assert parsed[3] is False


def test_mock_marker_cannot_cross_provider_boundary() -> None:
    dump = (
        "  Location Providers:\n"
        "    gps provider:\n"
        "      last location=Location[gps 35.7,51.4 age=0.0s]\n"
        "    network provider:\n"
        "      last location=Location[network 35.7,51.4 age=0.0s]\n"
        "  Mock Providers:\n"
        "    gps provider:\n"
        "      Mocked by cl.coders.faketraveler\n"
    )
    parsed = AdbLocationObserver.parse_dump(dump)
    assert parsed is not None
    assert parsed[0] == "network"
    assert parsed[3] is False


@pytest.mark.parametrize("reference", ["Last registered package:", "Mocked by"])
def test_unscoped_package_reference_is_not_an_active_mock_provider(reference: str) -> None:
    dump = "Location[gps 35.7,51.4 age=0.0s]\n" f"  {reference} cl.coders.faketraveler\n" "  Mock Providers:\n"
    parsed = AdbLocationObserver.parse_dump(dump)
    assert parsed is not None
    assert parsed[3] is False


@pytest.mark.parametrize("marker", ["mock", "mock=true", "isMock=true"])
def test_positive_marker_on_the_fix_is_preserved(marker: str) -> None:
    parsed = AdbLocationObserver.parse_dump(f"Location[gps 35.7,51.4 {marker} age=0.0s]")
    assert parsed is not None
    assert parsed[3] is True


@pytest.mark.parametrize(
    "elapsed,expected_age",
    [("+1m39s", 1.0), ("+1m40s", 0.0), ("+1m42s", 0.0), ("+1m42s001ms", None), ("+1d", None)],
)
def test_elapsed_timestamp_has_a_bounded_future_tolerance(elapsed: str, expected_age: float | None) -> None:
    parsed = AdbLocationObserver.parse_dump(f"Location[gps 35.7,51.4 mock et={elapsed}]", uptime_s=100.0)
    assert parsed is not None
    assert parsed[4] == expected_age


@pytest.mark.parametrize("uptime", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_invalid_uptime_cannot_establish_fix_freshness(uptime: float) -> None:
    parsed = AdbLocationObserver.parse_dump("Location[gps 35.7,51.4 mock et=+1s]", uptime_s=uptime)
    assert parsed is not None
    assert parsed[4] is None


@pytest.mark.parametrize("raw", ["nan 100", "inf 100", "-1 100", "invalid 100", ""])
def test_uptime_parser_does_not_substitute_idle_time_or_accept_nonfinite_values(raw: str) -> None:
    assert _parse_uptime_seconds(raw) is None


@pytest.mark.parametrize("elapsed", ["+1s045msjunk", "+1s.4m", "+" + "9" * 400 + "s"])
def test_malformed_elapsed_timestamp_cannot_establish_fix_freshness(elapsed: str) -> None:
    parsed = AdbLocationObserver.parse_dump(f"Location[gps 35.7,51.4 mock et={elapsed}]", uptime_s=100.0)
    assert parsed is not None
    assert parsed[4] is None
