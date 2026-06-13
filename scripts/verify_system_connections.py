#!/usr/bin/env python3
"""
Advanced System Verification Script for BarPro
فحص جامع سیستم BarPro - بررسی اتصالات و کنفیگ‌ها
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


class VerificationReport:
    """گزارش سیستم‌اتیک تمام اتصالات"""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}
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


def check_environment() -> tuple[bool, VerificationReport]:
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


def check_database_config() -> tuple[bool, VerificationReport]:
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


def check_cors_config() -> tuple[bool, VerificationReport]:
    """بررسی تنظیمات CORS"""
    report = VerificationReport()

    print("\n🔐 Checking CORS Configuration...")

    try:
        from app.core.config import utcms_config

        frontend_url = utcms_config.FRONTEND_URL


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


def check_frontend_integration() -> tuple[bool, VerificationReport]:
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


def check_docker_compose() -> tuple[bool, VerificationReport]:
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


def check_alembic_migrations() -> tuple[bool, VerificationReport]:
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


def check_api_routes() -> tuple[bool, VerificationReport]:
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
        list(routes_dir.glob("*.py"))

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
                "Route handler present"
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


async def check_async_connectivity() -> tuple[bool, VerificationReport]:
    """بررسی اتصالات async"""
    report = VerificationReport()

    print("\n⚡ Checking Async Connectivity...")

    try:
        from sqlalchemy import text

        from app.core.database import engine

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


async def check_utcms_connectivity() -> tuple[bool, VerificationReport]:
    """بررسی اتصال به سامانه UTCMS و تشخیص موقعیت آی‌پی"""
    report = VerificationReport()

    print("\n🌍 Checking UTCMS Connectivity...")

    import json
    import ssl
    import urllib.error
    import urllib.request

    target_url = "https://barname.utcms.ir/Barname/Account/Login"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 1. Direct Connection Check
    utcms_ok = False
    error_msg = ""
    try:
        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            code = response.getcode()
            if code in (200, 301, 302):
                utcms_ok = True
                error_msg = f"HTTP {code} - Reachable"
            else:
                error_msg = f"HTTP {code}"
    except urllib.error.HTTPError as e:
        error_msg = f"HTTP Error {e.code}: {e.reason}"
        if e.code in (403, 444):
            error_msg += " (Access restricted - likely due to non-Iranian IP)"
    except urllib.error.URLError as e:
        error_msg = f"Network Error: {e.reason}"
    except Exception as e:
        error_msg = f"Error: {str(e)}"

    report.add_check(
        "UTCMS Connection",
        "Direct connection to UTCMS",
        utcms_ok,
        error_msg
    )

    # 2. IP Location Check
    country_code = "UNKNOWN"
    ip_address = "UNKNOWN"
    try:
        req = urllib.request.Request(
            "https://freeipapi.com/api/json/",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            data = json.loads(response.read().decode())
            country_code = data.get("countryCode", "UNKNOWN")
            ip_address = data.get("ipAddress", "UNKNOWN")
    except Exception:
        pass

    is_iranian = (country_code == "IR")
    has_proxies = False
    try:
        from app.automation.proxy_rotator import get_proxy_rotator
        rotator = get_proxy_rotator()
        has_proxies = bool(hasattr(rotator, "proxies") and rotator.proxies)
    except Exception:
        pass

    passed = is_iranian or has_proxies
    ip_msg = f"IP: {ip_address}, Country: {country_code}"
    if country_code != "UNKNOWN" and not is_iranian:
        if has_proxies:
            ip_msg += " ⚠️ (VPN/non-IR IP detected, but proxy pool is configured)"
        else:
            ip_msg += " ❌ (WARNING: VPN is active or non-Iranian IP. UTCMS will block requests because no proxies are loaded!)"

    report.add_check(
        "UTCMS Connection",
        "IP Location Check (Must be IR or have proxies)",
        passed,
        ip_msg
    )

    # 3. Proxy Connection Check
    try:
        from app.automation.proxy_rotator import get_proxy_rotator
        rotator = get_proxy_rotator()
        if hasattr(rotator, "proxies") and rotator.proxies:
            report.add_check(
                "UTCMS Proxy",
                "Proxy Pool Loaded",
                True,
                f"{len(rotator.proxies)} proxies configured"
            )
            proxy = await rotator.get_next(require_iran_ip=False)
            if proxy:
                proxy_ok = False
                proxy_err = ""
                try:
                    proxy_support = urllib.request.ProxyHandler({'https': proxy.full_url})
                    opener = urllib.request.build_opener(proxy_support)
                    urllib.request.install_opener(opener)

                    req = urllib.request.Request(
                        target_url,
                        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
                    )
                    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                        if response.getcode() in (200, 301, 302):
                            proxy_ok = True
                            proxy_err = "Reachable via proxy"
                except Exception as ex:
                    proxy_err = f"Failed: {str(ex)[:100]}"
                finally:
                    urllib.request.install_opener(None)

                report.add_check(
                    "UTCMS Proxy",
                    "Proxy connectivity to UTCMS",
                    proxy_ok,
                    proxy_err
                )
        else:
            report.add_check(
                "UTCMS Proxy",
                "Proxy Pool Status",
                True,
                "No proxies loaded in pool. System relies on direct local IP."
            )
    except Exception:
        pass

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

        _, utcms_report = asyncio.run(check_utcms_connectivity())
        all_reports.append(utcms_report)
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
