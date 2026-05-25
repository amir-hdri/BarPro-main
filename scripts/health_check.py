#!/usr/bin/env python3
"""
Health check script for UTCMS Automation System
Verifies all critical components before deployment
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def check_environment():
    """Check environment variables"""
    print("🔍 Checking Environment Variables...")
    from app.core.config import utcms_config
    
    issues = []
    
    if not utcms_config.JWT_SECRET:
        issues.append("JWT_SECRET is not set")
    
    if not utcms_config.DRIVER_ENCRYPTION_KEY:
        issues.append("DRIVER_ENCRYPTION_KEY is not set")
    
    if not utcms_config.DATABASE_URL:
        issues.append("DATABASE_URL is not set")
    
    if not utcms_config.REDIS_URL:
        issues.append("REDIS_URL is not set")
    
    if issues:
        print("   ❌ Environment issues found:")
        for issue in issues:
            print(f"      - {issue}")
        return False
    
    print("   ✅ All environment variables are set")
    return True


def check_captcha():
    """Check captcha system"""
    print("\n🔍 Checking Captcha System...")
    from app.automation.captcha.barname_ml_solver import barname_ml_solver
    
    if not barname_ml_solver.model_path.exists():
        print(f"   ❌ Model file not found: {barname_ml_solver.model_path}")
        return False
    
    result = barname_ml_solver.warmup()
    if not result:
        print("   ❌ Failed to load captcha model")
        return False
    
    if not barname_ml_solver.available:
        print("   ❌ Captcha solver is not available")
        return False
    
    print(f"   ✅ Captcha model loaded successfully")
    print(f"      - Classes: {len(barname_ml_solver._classes)}")
    print(f"      - Device: {barname_ml_solver._device}")
    return True


def check_dependencies():
    """Check required dependencies"""
    print("\n🔍 Checking Dependencies...")
    
    required = {
        'torch': 'PyTorch',
        'cv2': 'OpenCV',
        'playwright': 'Playwright',
        'fastapi': 'FastAPI',
        'sqlalchemy': 'SQLAlchemy',
        'redis': 'Redis',
        'cryptography': 'Cryptography',
    }
    
    missing = []
    for module, name in required.items():
        try:
            __import__(module)
            print(f"   ✅ {name}")
        except ImportError:
            print(f"   ❌ {name} not installed")
            missing.append(name)
    
    return len(missing) == 0


def check_docker_config():
    """Check Docker configuration"""
    print("\n🔍 Checking Docker Configuration...")
    
    docker_compose = project_root / "docker-compose.yml"
    if not docker_compose.exists():
        print("   ❌ docker-compose.yml not found")
        return False
    
    dockerfile = project_root / "Dockerfile"
    if not dockerfile.exists():
        print("   ❌ Dockerfile not found")
        return False
    
    print("   ✅ Docker files present")
    return True


def main():
    """Run all health checks"""
    print("=" * 60)
    print("UTCMS Automation System - Health Check")
    print("=" * 60)
    
    checks = [
        check_environment,
        check_captcha,
        check_dependencies,
        check_docker_config,
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"   ❌ Check failed with error: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ All health checks passed!")
        print("=" * 60)
        return 0
    else:
        print("❌ Some health checks failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
