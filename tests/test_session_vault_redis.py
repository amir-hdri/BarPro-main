import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.session_vault import SessionVault, session_vault


@pytest.mark.asyncio
async def test_store_auth_state_from_file(tmp_path):
    temp_file = tmp_path / "utcms_state_testuser.json"
    temp_file.write_text(json.dumps({"cookies": [{"name": "sid"}]}))

    mock_redis = AsyncMock()
    with patch("app.core.redis.redis_manager.get", return_value=mock_redis):
        await session_vault.store_auth_state_from_file(str(temp_file), session_version=5, ttl=300)

        # Check that set was called with correct wrapper
        expected_key = "session:auth_state:utcms_state_testuser"
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == expected_key
        assert kwargs["ex"] == 300

        # Verify JSON content
        val = json.loads(args[1])
        assert val["session_version"] == 5
        assert val["playwright_state"] == {"cookies": [{"name": "sid"}]}


@pytest.mark.asyncio
async def test_save_driver_session_persists_context_state(tmp_path):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_context = AsyncMock()

    with (
        patch("app.core.redis.redis_manager.get", return_value=mock_redis),
        patch("app.services.session_vault.utcms_config.AUTH_STATE_PATH", str(tmp_path / "utcms_state.json")),
    ):
        vault = SessionVault()

        async def write_state(path):
            with open(path, "w", encoding="utf-8") as state_file:
                json.dump({"cookies": [{"name": "sid"}]}, state_file)

        mock_context.storage_state.side_effect = write_state
        await vault.save_driver_session(
            client_id=7,
            driver_id=9,
            username="driver-9",
            context=mock_context,
        )

    mock_context.storage_state.assert_awaited_once()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == "session:auth_state:utcms_state_client-7-driver-9-driver-9"
    stored = json.loads(args[1])
    assert stored["session_version"] == 1
    assert stored["playwright_state"] == {"cookies": [{"name": "sid"}]}


@pytest.mark.asyncio
async def test_save_driver_session_increments_existing_version(tmp_path):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"session_version": 7, "playwright_state": {}})
    mock_context = AsyncMock()

    with (
        patch("app.core.redis.redis_manager.get", return_value=mock_redis),
        patch("app.services.session_vault.utcms_config.AUTH_STATE_PATH", str(tmp_path / "utcms_state.json")),
    ):
        vault = SessionVault()

        async def write_state(path):
            with open(path, "w", encoding="utf-8") as state_file:
                json.dump({"cookies": [{"name": "fresh"}]}, state_file)

        mock_context.storage_state.side_effect = write_state
        await vault.save_driver_session(client_id=7, driver_id=9, username="driver-9", context=mock_context)

    stored = json.loads(mock_redis.set.call_args.args[1])
    assert stored["session_version"] == 8


@pytest.mark.asyncio
async def test_save_driver_session_is_noop_when_persistence_disabled():
    mock_context = AsyncMock()
    with patch("app.services.session_vault.utcms_config.USE_PERSISTENT_AUTH_STATE", False):
        assert await SessionVault().save_driver_session(7, 9, "driver-9", mock_context) is None
    mock_context.storage_state.assert_not_awaited()


def test_auth_state_exists_loads_from_redis(tmp_path):
    target_file = tmp_path / "utcms_state_testuser.json"
    assert not target_file.exists()

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = True
    mock_redis.get.return_value = json.dumps(
        {"session_version": 10, "playwright_state": {"cookies": [{"name": "sid"}]}}
    )

    with patch("app.core.redis.redis_manager.get", return_value=mock_redis):
        exists = session_vault.auth_state_exists(str(target_file))
        assert exists is True
        assert not target_file.exists()

        restored = session_vault.restore_auth_state_to_file_sync(str(target_file))
        assert restored is True
        assert target_file.exists()

        # Should only write the playwright_state part to the file
        content = json.loads(target_file.read_text())
        assert content == {"cookies": [{"name": "sid"}]}


def test_delete_auth_state_clears_redis_and_disk(tmp_path):
    target_file = tmp_path / "utcms_state_testuser.json"
    target_file.write_text("dummy")

    mock_redis = AsyncMock()
    with patch("app.core.redis.redis_manager.get", return_value=mock_redis):
        session_vault.delete_auth_state(str(target_file))

        # Deleted from Redis
        mock_redis.delete.assert_called_once_with("session:auth_state:utcms_state_testuser")
        # Deleted from disk
        assert not target_file.exists()


def test_get_session_version():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"session_version": 42, "playwright_state": {}})

    with patch("app.core.redis.redis_manager.get", return_value=mock_redis):
        version = session_vault.get_session_version("/tmp/utcms_state_testuser.json")
        assert version == 42


def test_session_vault_fail_closed_if_redis_down(tmp_path):
    target_file = tmp_path / "utcms_state_testuser.json"

    # Simulate redis connection error
    mock_redis = AsyncMock()
    mock_redis.exists.side_effect = Exception("Redis connection refused")

    with patch("app.core.redis.redis_manager.get", return_value=mock_redis):
        with pytest.raises(RuntimeError, match="Session vault access error"):
            session_vault.auth_state_exists(str(target_file))
