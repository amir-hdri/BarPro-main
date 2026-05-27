from unittest.mock import patch

from app.automation.stealth import _UA_POOL, get_random_user_agent


def test_get_random_user_agent():
    """Test get_random_user_agent returns a valid user agent from the pool."""
    # Test normal functionality multiple times
    for _ in range(10):
        ua = get_random_user_agent()
        assert isinstance(ua, str)
        assert any(ua == pool_item[0] for pool_item in _UA_POOL)

    # Test with mocked random.choice
    mock_ua_entry = ("Mocked/User.Agent (Test)", "mock", "100")
    with patch("app.automation.stealth.random.choice", return_value=mock_ua_entry):
        ua = get_random_user_agent()
        assert ua == "Mocked/User.Agent (Test)"
