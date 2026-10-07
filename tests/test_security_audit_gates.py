"""Behavioral checks for the security scanner findings from the October audit."""

import hashlib
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.automation import http_browser_bridge as bridge
from app.automation.captcha import debug_artifacts as artifacts
from app.automation.utcms_mobile_client import UtcmsMobileClient
from app.core.private_storage import private_directory, write_private_file

pytestmark = pytest.mark.unit


def test_private_storage_stays_pinned_when_directory_path_is_replaced(tmp_path: Path) -> None:
    original = tmp_path / "cache"
    renamed = tmp_path / "original-cache"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    with private_directory(original) as directory_fd:
        original.rename(renamed)
        original.symlink_to(replacement, target_is_directory=True)
        write_private_file(directory_fd, "asset", b"trusted", replace=True)
    assert (renamed / "asset").read_bytes() == b"trusted"
    assert list(replacement.iterdir()) == []


def test_cache_rejects_mixed_metadata_and_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "_ASSET_CACHE_DIR", tmp_path / "cache")
    bridge._write_asset_cache("key", 200, {}, b"first")
    _meta, body = bridge._asset_cache_files("key")
    body.write_bytes(b"second")
    assert bridge._read_asset_cache("key") is None


def test_captcha_artifacts_do_not_follow_directory_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "output"
    output.symlink_to(target, target_is_directory=True)
    result = artifacts.save_rejection_artifact("aGVsbG8=", prediction="5", result_code=4003, directory=output)
    assert result is None
    assert list(target.iterdir()) == []


def test_captcha_answers_never_enter_logs_or_metadata(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    answer = "649827"
    expression = "649826 + 1"
    result = artifacts.save_rejection_artifact(
        "aGVsbG8=",
        prediction=answer,
        expression=expression,
        result_code=4003,
        provider="cnn",
        confidence=0.9,
        directory=tmp_path,
        extra={"attempt": 2, "prediction": answer, "debug": {"expression": expression}},
    )
    assert result is not None
    metadata = result.read_text()
    assert answer not in metadata + caplog.text
    assert expression not in metadata + caplog.text
    payload = json.loads(metadata)
    assert payload["extra"] == {"attempt": 2}
    assert payload["image_sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert payload["image_bytes"] == 5
    assert Path(payload["image_png"]).read_bytes() == b"hello"


def test_captcha_artifacts_are_private_and_unique_under_concurrency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "artifacts"
    directory.mkdir(mode=0o755)
    monkeypatch.setattr(artifacts.time, "strftime", lambda *args: "audit-stamp")
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    (directory / "audit-stamp.png").symlink_to(victim)

    def save(index: int) -> Path | None:
        return artifacts.save_rejection_artifact(
            "aGVsbG8=", prediction=str(index), result_code=4003, directory=directory
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(save, range(12)))
    assert None not in results
    assert len(set(results)) == 12
    assert victim.read_text() == "unchanged"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in results:
        assert path is not None
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        payload = json.loads(path.read_text())
        image = Path(payload["image_png"])
        assert image.read_bytes() == b"hello"
        assert stat.S_IMODE(image.stat().st_mode) == 0o600


def test_cache_atomic_writes_never_follow_a_planted_scratch_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o755)
    monkeypatch.setattr(bridge, "_ASSET_CACHE_DIR", cache)
    key = "https://example.invalid/asset.js?v=1"
    _meta, body = bridge._asset_cache_files(key)
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    body.with_suffix(".body.tmp").symlink_to(victim)

    bridge._write_asset_cache(key, 200, {"content-type": "text/javascript"}, b"safe-asset")

    assert victim.read_text() == "unchanged"
    assert bridge._read_asset_cache(key) == (200, {"content-type": "text/javascript"}, b"safe-asset")
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    assert stat.S_IMODE(body.stat().st_mode) == 0o600


@pytest.mark.parametrize("entry", ["body", "meta"])
def test_cache_reads_refuse_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str) -> None:
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    monkeypatch.setattr(bridge, "_ASSET_CACHE_DIR", cache)
    key = "https://example.invalid/asset.js?v=1"
    meta, body = bridge._asset_cache_files(key)
    meta.write_text(json.dumps({"status": 200, "headers": {}, "url_key": key}))
    body.write_bytes(b"legitimate")
    path = body if entry == "body" else meta
    victim = tmp_path / "injected"
    victim.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(victim)
    assert bridge._read_asset_cache(key) is None


def test_cache_refuses_untrusted_directory_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "shared-cache"
    cache.mkdir()
    cache.chmod(0o777)
    monkeypatch.setattr(bridge, "_ASSET_CACHE_DIR", cache)
    bridge._write_asset_cache("key", 200, {}, b"asset")
    assert list(cache.iterdir()) == []


def test_parallel_cache_writes_keep_complete_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "_ASSET_CACHE_DIR", tmp_path / "cache")

    def save(index: int) -> None:
        bridge._write_asset_cache("same-key", 200, {"revision": str(index)}, str(index).encode())

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(save, range(20)))
    cached = bridge._read_asset_cache("same-key")
    # Pair replacement may overlap; inconsistent pairs must be a cache miss.
    if cached is not None:
        assert cached[2].decode() == cached[1]["revision"]


@pytest.mark.parametrize("kind", ["dnt", "math"])
def test_shipped_captcha_models_load_with_explicit_restricted_unpickling(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    torch = pytest.importorskip("torch")
    from app.automation.captcha.dnt_captcha_solver import DntCaptchaProvider
    from app.automation.captcha.math_crnn_solver import MathCrnnSolver

    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    load = Mock(wraps=torch.load)
    monkeypatch.setattr(torch, "load", load)
    if kind == "dnt":
        solver = DntCaptchaProvider()
        assert solver._load_model()
        assert solver._initialized
    else:
        solver = MathCrnnSolver()
        assert solver.available
    assert load.call_args.kwargs["weights_only"] is True
    assert len(solver._model.state_dict()) == 53


@pytest.mark.parametrize("kind", ["dnt", "math"])
def test_captcha_models_reject_unsupported_checkpoint_format(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    torch = pytest.importorskip("torch")
    from app.automation.captcha.dnt_captcha_solver import DntCaptchaProvider
    from app.automation.captcha.math_crnn_solver import MathCrnnSolver

    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    model = tmp_path / "invalid.pth"
    torch.save({"model_state": [1, 2, 3]}, model)
    if kind == "dnt":
        solver = DntCaptchaProvider()
        solver.model_path = model
        assert solver._load_model() is False
    else:
        solver = MathCrnnSolver(model_path=model)
        assert solver.available is False


async def test_mobile_security_key_preserves_utf8_json_wire_contract() -> None:
    body = {"note": "تهران", "count": 2}
    response = Mock(status_code=200, text="{}")
    response.json.return_value = {}
    http_client = Mock(get=AsyncMock(return_value=response))
    client = UtcmsMobileClient(base_url="https://example.invalid/API", http_client=http_client)
    expected = "84ce6515ff1fdd0a6419f69014e6a2b2"
    assert client._headers(body)["SecurityKey"] == expected
    await client._get("/example", params=body)
    assert http_client.get.call_args.kwargs["headers"]["SecurityKey"] == expected
