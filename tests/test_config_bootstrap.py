import importlib.util
from pathlib import Path


def test_config_bootstrap_applies_generated_secrets_before_instantiating_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("DRIVER_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    import app.core.config as config_module

    spec = importlib.util.spec_from_file_location("temp_config_bootstrap", Path(config_module.__file__))
    temp_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(temp_module)

    assert temp_module.utcms_config.JWT_SECRET != "change-me-jwt-secret-required"
    assert temp_module.utcms_config.DRIVER_ENCRYPTION_KEY != "change-me-encryption-key-required"

    env_contents = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "JWT_SECRET=" in env_contents
    assert "DRIVER_ENCRYPTION_KEY=" in env_contents
