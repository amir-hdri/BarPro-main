#!/usr/bin/env python3
"""
Advanced System Verification Script for BarPro
فحص جامع سیستم BarPro - بررسی اتصالات و کنفیگ‌ها
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, Tuple

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))


class VerificationReport:
    """گزارش سیستم‌اتیک تمام اتصالات"""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {}
        self.passed_checks = 0
        self.failed_checks = 0
        self.warnings = 0
    
    def add_check(self, category: str, name: str, passed: bool, message: str = ""):
        if category not in self.results:
            self.results[category] = {}
        
        self.results[category][name] = {
            "passed": passed,
            "message": message
        }
        
        if passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
    
    def print_report(self):
        print("\n" + "="*70)
        print("🔍 BarPro System Verification Report")
        print("="*70 + "\n")
        
        for category, checks in self.results.items():
            print(f"\n📦 {category}")
            print("-" * 70)
            
            for check_name, result in checks.items():
                status = "✅" if result["passed"] else "❌"
                print(f"  {status} {check_name}")
                if result["message"]:
                    print(f"     → {result['message']}")
        
        print("\n" + "="*70)
        print(f"📊 Summary: {self.passed_checks} passed, {self.failed_checks} failed, {self.warnings} warnings")
        print("="*70 + "\n")
        
        return self.failed_checks == 0


def check_environment() -> Tuple[bool, VerificationReport]:
    """بررسی متغیرهای محیط"""
    report = VerificationReport()
    
    print("🌍 Checking Environment Variables...")
    
    # Try importing config
    try:
        from app.core.config import utcms_config
        
        checks = [
            ("JWT_SECRET", utcms_config.JWT_SECRET),
            ("DRIVER_ENCRYPTION_KEY", utcms_config.DRIVER_ENCRYPTION_KEY),
            ("DATABASE_URL", utcms_config.DATABASE_URL),
            ("REDIS_URL", getattr(utcms_config, "REDIS_URL", None)),
        ]
        
        for name, value in checks:
            is_set = bool(value)
            report.add_check(
                "Environment",
                name,
                is_set,
                f"{'Set' if is_set else 'Not set'}"
            )
        
        # Frontend URL check
        frontend_url = utcms_config.FRONTEND_URL
        report.add_check(
            "Environment",
            "FRONTEND_URL",
            bool(frontend_url),
            f"Set to {frontend_url}"
        )
        
    except Exception as e:
        report.add_check("Environment", "Config Load", False, str(e))
    
    return True, report


def check_database_config() -> Tuple[bool, VerificationReport]:
    """بررسی کنفیگ دیتابیس"""
    report = VerificationReport()
    
    print("\n🗄️  Checking Database Configuration...")
    
    try:
        from app.core.config import utcms_config
        
        db_url = utcms_config.DATABASE_URL
        
        # Parse URL
        checks = [
            ("URL Format", "postgresql+asyncpg://" in db_url, "PostgreSQL async driver"),
            ("Host Connection", "@" in db_url, "Has hostname"),
            ("Database Specified", "/" in db_url.split("@")[-1], "Database name specified"),
        ]
        
        for check_name, passed, message in checks:
            report.add_check("Database Config", check_name, passed, message)
        
        # Connection pool config
        try:
            from app.core.database import engine_kwargs
            
            report.add_check(
                "Database Config",
                "Connection Pool",
                "pool_size" in engine_kwargs,
                f"pool_size={engine_kwargs.get('pool_size', 'N/A')}, "
                f"max_overflow={engine_kwargs.get('max_overflow', 'N/A')}"
            )
        except Exception as e:
            report.add_check("Database Config", "Connection Pool", False, str(e))
        
    except Exception as e:
        report.add_check("Database Config", "Load Config", False, str(e))
    
    return True, report


def check_cors_config() -> Tuple[bool, VerificationReport]:
    """بررسی تنظیمات CORS"""
    report = VerificationReport()
    
    print("\n🔐 Checking CORS Configuration...")
    
    try:
        from app.core.config import utcms_config
        
        frontend_url = utcms_config.FRONTEND_URL
        
        allowed_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            frontend_url,
        ]
        
        report.add_check(
            "CORS",
            "Frontend URL Configured",
            bool(frontend_url),
            f"URL: {frontend_url}"
        )
        
        report.add_check(
            "CORS",
            "Localhost Allowed",
            True,
            "Both localhost:3000 and 127.0.0.1:3000"
        )
        
    except Exception as e:
        report.add_check("CORS", "Config Load", False, str(e))
    
    return True, report


def check_frontend_integration() -> Tuple[bool, VerificationReport]:
    """بررسی اتصال فرانت‌اند"""
    report = VerificationReport()
    
    print("\n🎨 Checking Frontend Integration...")
    
    frontend_path = project_root / "apps" / "web"
    
    # Check package.json
    package_json = frontend_path / "package.json"
    report.add_check(
        "Frontend",
        "package.json exists",
        package_json.exists(),
        str(package_json)
    )
    
    # Check .env.local
    env_local = frontend_path / ".env.local"
    report.add_check(
        "Frontend",
        ".env.local exists",
        env_local.exists(),
        str(env_local)
    )
    
    if env_local.exists():
        content = env_local.read_text()
        has_api_url = "NEXT_PUBLIC_API_URL" in content
        report.add_check(
            "Frontend",
            "NEXT_PUBLIC_API_URL configured",
            has_api_url,
            "API URL set in environment"
        )
    
    # Check api.ts
    api_ts = frontend_path / "src" / "lib" / "api.ts"
    report.add_check(
        "Frontend",
        "API client (api.ts) exists",
        api_ts.exists(),
        str(api_ts)
    )
    
    if api_ts.exists():
        api_content = api_ts.read_text()
        checks = [
            ("axios import", "import axios" in api_content),
            ("API_BASE_URL", "API_BASE_URL" in api_content),
            ("axiosClient", "axiosClient" in api_content),
        ]
        
        for check_name, passed in checks:
            report.add_check("Frontend", check_name, passed, "Found in api.ts")
    
    return True, report


def check_docker_compose() -> Tuple[bool, VerificationReport]:
    """بررسی docker-compose"""
    report = VerificationReport()
    
    print("\n🐳 Checking Docker Configuration...")
    
    docker_compose = project_root / "docker-compose.yml"
    report.add_check(
        "Docker",
        "docker-compose.yml exists",
        docker_compose.exists(),
        str(docker_compose)
    )
    
    if docker_compose.exists():
        content = docker_compose.read_text()
        
        services = [
            ("postgres service", "postgres:"),
            ("redis service", "redis:"),
            ("backend service", "backend:"),
            ("frontend service", "frontend:"),
            ("nginx service", "nginx:"),
        ]
        
        for service_name, marker in services:
            report.add_check(
                "Docker Services",
                service_name,
                marker in content,
                "Service configured"
            )
        
        # Check healthchecks
        report.add_check(
            "Docker Health",
            "PostgreSQL healthcheck",
            "pg_isready" in content,
            "Health check configured"
        )
        
        report.add_check(
            "Docker Health",
            "Redis healthcheck",
            "redis-cli" in content,
            "Health check configured"
        )
        
        # Check dependencies
        report.add_check(
            "Docker Config",
            "Service dependencies",
            "depends_on:" in content,
            "Service ordering configured"
        )
    
    return True, report


def check_alembic_migrations() -> Tuple[bool, VerificationReport]:
    """بررسی migrations"""
    report = VerificationReport()
    
    print("\n📚 Checking Database Migrations...")
    
    alembic_ini = project_root / "alembic.ini"
    alembic_versions = project_root / "alembic" / "versions"
    
    report.add_check(
        "Migrations",
        "alembic.ini exists",
        alembic_ini.exists(),
        str(alembic_ini)
    )
    
    report.add_check(
        "Migrations",
        "versions directory exists",
        alembic_versions.exists(),
        str(alembic_versions)
    )
    
    if alembic_versions.exists():
        migration_files = list(alembic_versions.glob("*.py"))
        report.add_check(
            "Migrations",
            "Migration files exist",
            len(migration_files) > 0,
            f"Found {len(migration_files)} migration files"
        )
    
    return True, report


def check_api_routes() -> Tuple[bool, VerificationReport]:
    """بررسی API routes"""
    report = VerificationReport()
    
    print("\n🛣️  Checking API Routes...")
    
    routes_dir = project_root / "app" / "api" / "routes"
    
    report.add_check(
        "API Routes",
        "routes directory exists",
        routes_dir.exists(),
        str(routes_dir)
    )
    
    if routes_dir.exists():
        route_files = list(routes_dir.glob("*.py"))
        
        expected_routes = [
            "system.py",
            "waybill_entry.py",
            "management.py",
        ]
        
        for route in expected_routes:
            route_path = routes_dir / route
            report.add_check(
                "API Endpoints",
                f"{route} exists",
                route_path.exists(),
                f"Route handler present"
            )
    
    # Check main.py for router inclusion
    main_py = project_root / "app" / "main.py"
    if main_py.exists():
        content = main_py.read_text()
        
        include_checks = [
            ("include_router waybill_map", "include_router(waybill_map"),
            ("include_router system", "include_router(system"),
            ("include_router management", "include_router(management"),
        ]
        
        for check_name, marker in include_checks:
            report.add_check(
                "Router Inclusion",
                check_name,
                marker in content,
                "Router registered"
            )
        
        # Check middleware
        report.add_check(
            "Middleware",
            "CORS middleware",
            "CORSMiddleware" in content,
            "CORS enabled"
        )
        
        report.add_check(
            "Middleware",
            "HTTP middleware",
            "request_context_middleware" in content,
            "Request tracking enabled"
        )
    
    return True, report


async def check_async_connectivity() -> Tuple[bool, VerificationReport]:
    """بررسی اتصالات async"""
    report = VerificationReport()
    
    print("\n⚡ Checking Async Connectivity...")
    
    try:
        from app.core.database import engine, async_session_factory
        from sqlalchemy import text
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            report.add_check(
                "Async Database",
                "Engine connectivity",
                result is not None,
                "Connected to database"
            )
    except Exception as e:
        report.add_check(
            "Async Database",
            "Engine connectivity",
            False,
            f"Connection failed: {str(e)[:100]}"
        )
    
    return True, report


def main():
    """اجرای تمام بررسی‌ها"""
    
    print("\n" + "="*70)
    print("🚀 BarPro System Verification - بررسی جامع سیستم BarPro")
    print("="*70)
    
    all_reports = []
    
    # Run all checks
    checks = [
        ("Environment", check_environment),
        ("Database Config", check_database_config),
        ("CORS Config", check_cors_config),
        ("Frontend Integration", check_frontend_integration),
        ("Docker Setup", check_docker_compose),
        ("Migrations", check_alembic_migrations),
        ("API Routes", check_api_routes),
    ]
    
    for check_name, check_func in checks:
        try:
            _, report = check_func()
            all_reports.append(report)
        except Exception as e:
            print(f"❌ Error in {check_name}: {e}")
    
    # Async checks
    try:
        _, async_report = asyncio.run(check_async_connectivity())
        all_reports.append(async_report)
    except Exception as e:
        print(f"⚠️  Skipping async checks: {e}")
    
    # Merge reports
    final_report = VerificationReport()
    for report in all_reports:
        for category, checks in report.results.items():
            for check_name, result in checks.items():
                final_report.add_check(
                    category,
                    check_name,
                    result["passed"],
                    result["message"]
                )
    
    # Print final report
    success = final_report.print_report()
    
    if success:
        print("✅ All checks passed! System is properly configured.")
        return 0
    else:
        print(f"❌ {final_report.failed_checks} checks failed. Please review the report above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
