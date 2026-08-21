import pytest

from app.automation.auth_utils import get_captcha_strategy_order
from app.core.config import _validated_choice


@pytest.mark.parametrize(
    ("mode", "fallback", "expected"),
    [
        ("local_only", True, ("math", "provider")),
        ("provider_only", True, ("provider",)),
        ("provider_first", True, ("provider", "math")),
        ("provider_first", False, ("provider",)),
        ("manual_only", True, ()),
    ],
)
def test_captcha_strategy_contract(mode: str, fallback: bool, expected: tuple[str, ...]) -> None:
    assert get_captcha_strategy_order(mode, fallback) == expected


@pytest.mark.parametrize("mode", ["worker_first", "clean_pool_only", "hybrid"])
def test_valid_egress_modes(mode: str) -> None:
    assert (
        _validated_choice("EGRESS_PROXY_MODE", mode, "worker_first", {"worker_first", "clean_pool_only", "hybrid"})
        == mode
    )


@pytest.mark.parametrize("mode", ["clean_pool", "round_robin", "", "direct"])
def test_invalid_egress_modes_fail_fast(mode: str) -> None:
    with pytest.raises(ValueError, match="Invalid EGRESS_PROXY_MODE"):
        _validated_choice("EGRESS_PROXY_MODE", mode, "worker_first", {"worker_first", "clean_pool_only", "hybrid"})


def test_invalid_captcha_mode_fails_fast() -> None:
    with pytest.raises(ValueError, match="Invalid CAPTCHA_MODE"):
        _validated_choice(
            "CAPTCHA_MODE",
            "manual_fallback",
            "local_only",
            {"local_only", "provider_only", "provider_first", "manual_only"},
        )
