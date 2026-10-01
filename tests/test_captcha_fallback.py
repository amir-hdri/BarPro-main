"""Tests for the CompositeCaptchaProvider fallback chain.

The composite tries providers in order and returns the first success. A single
provider must never break the chain: an exception from one provider must be
absorbed so the remaining providers still get tried.
"""

from unittest.mock import AsyncMock

import pytest

from app.automation.captcha import CompositeCaptchaProvider
from app.automation.captcha.base import CaptchaProvider, CaptchaResult


def _provider(name: str, result: CaptchaResult | None = None, exc: Exception | None = None):
    p = AsyncMock(spec=CaptchaProvider)
    type(p).__name__ = name
    if exc is not None:
        p.solve_text_captcha.side_effect = exc
    else:
        p.solve_text_captcha.return_value = result
    return p


@pytest.mark.asyncio
async def test_first_success_wins():
    winner = CaptchaResult(solved=True, provider="p1", value="42")
    composite = CompositeCaptchaProvider(
        [
            _provider("p1", winner),
            _provider("p2", CaptchaResult(solved=True, provider="p2", value="99")),
        ]
    )
    result = await composite.solve_text_captcha("img")
    assert result.solved is True
    assert result.value == "42"


@pytest.mark.asyncio
async def test_falls_through_unsolved_to_next_provider():
    composite = CompositeCaptchaProvider(
        [
            _provider("p1", CaptchaResult(solved=False, provider="p1", error="low_conf")),
            _provider("p2", CaptchaResult(solved=True, provider="p2", value="7")),
        ]
    )
    result = await composite.solve_text_captcha("img")
    assert result.solved is True
    assert result.value == "7"


@pytest.mark.asyncio
async def test_raising_provider_does_not_break_chain():
    """A provider that raises must be skipped, not abort the fallback chain."""
    good = _provider("p2", CaptchaResult(solved=True, provider="p2", value="13"))
    composite = CompositeCaptchaProvider(
        [
            _provider("p1", exc=RuntimeError("torch exploded")),
            good,
        ]
    )
    result = await composite.solve_text_captcha("img")
    assert result.solved is True
    assert result.value == "13"
    good.solve_text_captcha.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_fail_returns_last_result_not_raise():
    composite = CompositeCaptchaProvider(
        [
            _provider("p1", exc=RuntimeError("boom")),
            _provider("p2", CaptchaResult(solved=False, provider="p2", error="nope")),
        ]
    )
    result = await composite.solve_text_captcha("img")
    assert result.solved is False


@pytest.mark.asyncio
async def test_empty_provider_list():
    result = await CompositeCaptchaProvider([]).solve_text_captcha("img")
    assert result.solved is False
    assert result.error == "no_provider"
