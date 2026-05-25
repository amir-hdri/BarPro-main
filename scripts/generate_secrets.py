#!/usr/bin/env python3
"""Generate secure secrets for UTCMS Automation."""
import secrets
from cryptography.fernet import Fernet


def generate_all_secrets():
    """Generate all required secrets."""
    print("=" * 60)
    print("UTCMS Automation - Secret Generator")
    print("=" * 60)
    print()
    
    print("Add these to your .env file:")
    print()
    
    print("# JWT Secret (for authentication tokens)")
    jwt_secret = secrets.token_hex(32)
    print(f"JWT_SECRET={jwt_secret}")
    print()
    
    print("# Driver Encryption Key (for encrypting driver credentials)")
    encryption_key = Fernet.generate_key().decode()
    print(f"DRIVER_ENCRYPTION_KEY={encryption_key}")
    print()
    
    print("# API Key (for API authentication)")
    api_key = secrets.token_urlsafe(32)
    print(f"API_KEY={api_key}")
    print()
    
    print("# Database Password")
    db_password = secrets.token_urlsafe(24)
    print(f"POSTGRES_PASSWORD={db_password}")
    print()
    
    print("# Redis Password")
    redis_password = secrets.token_urlsafe(24)
    print(f"REDIS_PASSWORD={redis_password}")
    print()
    
    print("=" * 60)
    print("⚠️  IMPORTANT: Keep these secrets secure!")
    print("   - Never commit them to version control")
    print("   - Store them in a secure password manager")
    print("   - Rotate them regularly (every 90 days)")
    print("=" * 60)


if __name__ == "__main__":
    generate_all_secrets()
