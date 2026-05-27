from typing import Any

from fastapi import APIRouter, Depends

from app.automation.reporting import report_service
from app.core.security import require_sensitive_auth

router = APIRouter(prefix="/reports", tags=["گزارشات"])


@router.get("/summary", summary="خلاصه آمار ربات", dependencies=[Depends(require_sensitive_auth)])
async def get_summary_report() -> dict[str, Any]:
    """دریافت آمار کلی عملکرد ربات با تحلیل روند"""
    return await report_service.get_summary()


@router.get("/daily", summary="گزارش روزانه فعالیت", dependencies=[Depends(require_sensitive_auth)])
async def get_daily_report() -> dict[str, Any]:
    """دریافت گزارش تفکیکی روزانه (موفقیت/شکست)"""
    return await report_service.get_daily_report()


@router.get("/operational", summary="شاخص‌های عملیاتی", dependencies=[Depends(require_sensitive_auth)])
async def get_operational_report() -> dict[str, Any]:
    """دریافت شاخص‌های latency/error/mode برای پایش عملیاتی."""
    return await report_service.get_operational_report()


@router.get("/errors", summary="تحلیل خطاها", dependencies=[Depends(require_sensitive_auth)])
async def get_error_analysis() -> dict[str, Any]:
    """دریافت تحلیل جامع خطاها با دسته‌بندی و نمونه‌ها"""
    return await report_service.get_error_analysis()


@router.get("/performance", summary="داشبورد عملکرد", dependencies=[Depends(require_sensitive_auth)])
async def get_performance_dashboard() -> dict[str, Any]:
    """دریافت معیارهای کلیدی عملکرد شامل RPM و آپتایم"""
    return await report_service.get_performance_dashboard()
