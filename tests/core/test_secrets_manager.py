import string

from app.core.secrets_manager import generate_secure_secret


def test_generate_secure_secret_length():
    """Test that generate_secure_secret creates a string of the requested length."""
    assert len(generate_secure_secret(32)) == 32
    assert len(generate_secure_secret(64)) == 64
    assert len(generate_secure_secret(128)) == 128

def test_generate_secure_secret_default_length():
    """Test that default length is 64."""
    assert len(generate_secure_secret()) == 64

def test_generate_secure_secret_alphabet():
    """Test that characters are drawn from the correct alphabet."""
    expected_alphabet = set(string.ascii_letters + string.digits + "!@#$%^&*()-_=+")
    secret = generate_secure_secret(1000)  # Generate a long string to test multiple chars

    for char in secret:
        assert char in expected_alphabet

def test_generate_secure_secret_randomness():
    """Test that multiple calls generate different secrets."""
    secret1 = generate_secure_secret()
    secret2 = generate_secure_secret()
    assert secret1 != secret2
