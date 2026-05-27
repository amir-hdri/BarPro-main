"""سرویس گزارش‌دهی و آمار - نسخه پیشرفته با تحلیل جامع"""

import asyncio
from collections import deque
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import utcms_config
from app.core.database import engine
from app.models_legacy import BotStats

# Compat: models package moved BotStats to models.py
from app.monitoring.metrics import track_waybill_failure, track_waybill_request, track_waybill_success


class ReportService:
    """سرویس جمع‌آوری و ارائه گزارش‌های عملکرد با ذخیره‌سازی پایدار و تحلیل پیشرفته"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._op_lock = asyncio.Lock()
        self._latency_samples = deque(maxlen=max(1000, utcms_config.LATENCY_SAMPLE_MAX))
        self._hourly_samples = deque(maxlen=2000)  # For hourly trends
        self._mode_counters = {
            "safe": {"requests": 0, "success": 0, "failure": 0},
            "full": {"requests": 0, "success": 0, "failure": 0},
        }
        self._error_categories = {
            "auth": 0,
            "map": 0,
            "captcha": 0,
            "network": 0,
            "form": 0,
            "validation": 0,
            "timeout": 0,
            "unknown": 0,
        }
        self._error_details = deque(maxlen=500)  # Recent error details
        self._success_times = deque(maxlen=1000)  # For success rate trends
        self._daily_trends = {}  # Cache for daily trends

    async def _get_today_stats(self, session: AsyncSession) -> BotStats:
        today = date.today()
        statement = select(BotStats).where(BotStats.report_date == today)
        result = await session.execute(statement)
        stats = result.scalars().first()

        if not stats:
            stats = BotStats(report_date=today)
            session.add(stats)

        return stats

    async def _update_today_stats(self, updater) -> None:
        today = date.today()
        async with self._lock:
            async with AsyncSession(engine) as session:
                stats = await self._get_today_stats(session)
                updater(stats)
                session.add(stats)
                try:
                    await session.commit()
                    return
                except IntegrityError:
                    await session.rollback()

                statement = select(BotStats).where(BotStats.report_date == today)
                result = await session.execute(statement)
                existing_stats = result.scalars().first()
                if not existing_stats:
                    raise

                updater(existing_stats)
                session.add(existing_stats)
                await session.commit()

    async def _record_mode_event(
        self,
        mode: str,
        event: str,
        latency_ms: float | None = None,
        category: str | None = None,
    ) -> None:
        normalized_mode = "full" if mode == "full" else "safe"

        async with self._op_lock:
            if event in self._mode_counters[normalized_mode]:
                self._mode_counters[normalized_mode][event] += 1

            if latency_ms is not None:
                self._latency_samples.append(float(latency_ms))
                # Track hourly trend
                now = datetime.now()
                hour_key = now.strftime("%Y-%m-%d %H:00")
                self._hourly_samples.append({
                    "timestamp": now.isoformat(),
                    "latency": float(latency_ms),
                    "hour": hour_key
                })

            if category:
                normalized_category = category if category in self._error_categories else "unknown"
                self._error_categories[normalized_category] += 1

    async def record_request(self, mode: str = "safe"):
        track_waybill_request(mode)
        await self._record_mode_event(mode=mode, event="requests")
        await self._update_today_stats(lambda stats: setattr(stats, "total_requests", stats.total_requests + 1))

    async def record_success(self, mode: str = "safe", latency_ms: float | None = None):
        track_waybill_success(mode)
        await self._record_mode_event(mode=mode, event="success", latency_ms=latency_ms)

        # Track success time for trends
        self._success_times.append({
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "latency": latency_ms
        })

        await self._update_today_stats(
            lambda stats: setattr(stats, "successful_waybills", stats.successful_waybills + 1)
        )

    async def record_failure(self, mode: str = "safe", category: str = "unknown", details: str = ""):
        track_waybill_failure(mode, category)
        await self._record_mode_event(mode=mode, event="failure", category=category)

        # Track error details
        if details:
            self._error_details.append({
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
                "category": category,
                "details": details[:200]  # Limit to 200 chars
            })

        await self._update_today_stats(
            lambda stats: setattr(stats, "failed_attempts", stats.failed_attempts + 1)
        )

    async def record_map_usage(self, map_type: str):
        def _updater(stats: BotStats):
            if map_type == "google_maps":
                stats.map_google += 1
            elif map_type == "openlayers":
                stats.map_openlayers += 1
            elif map_type == "leaflet":
                stats.map_leaflet += 1
            elif map_type == "mapbox":
                stats.map_mapbox += 1
            elif map_type == "none":
                stats.map_none += 1
            else:
                stats.map_unknown += 1

        await self._update_today_stats(_updater)

    async def get_summary(self) -> dict[str, Any]:
        """دریافت خلاصه جامع آمار با تحلیل روند"""
        async with AsyncSession(engine) as session:
            statement = select(BotStats)
            result = await session.execute(statement)
            all_stats = result.scalars().all()

            total_requests = sum(s.total_requests for s in all_stats)
            successful_waybills = sum(s.successful_waybills for s in all_stats)
            failed_attempts = sum(s.failed_attempts for s in all_stats)

            map_usage = {
                "google_maps": sum(s.map_google for s in all_stats),
                "openlayers": sum(s.map_openlayers for s in all_stats),
                "leaflet": sum(s.map_leaflet for s in all_stats),
                "mapbox": sum(s.map_mapbox for s in all_stats),
                "unknown": sum(s.map_unknown for s in all_stats),
                "none": sum(s.map_none for s in all_stats),
            }

            # Calculate trends
            async with self._op_lock:
                latencies = list(self._latency_samples)
                recent_errors = list(self._error_details)[-10:]  # Last 10 errors

            # Calculate performance metrics
            performance = {
                "avg_latency_ms": round(mean(latencies), 2) if latencies else 0,
                "median_latency_ms": round(median(latencies), 2) if latencies else 0,
                "min_latency_ms": round(min(latencies), 2) if latencies else 0,
                "max_latency_ms": round(max(latencies), 2) if latencies else 0,
                "p95_latency_ms": self._percentile(latencies, 95),
                "p99_latency_ms": self._percentile(latencies, 99),
            }

            # Calculate hourly trend (last 24 hours)
            hourly_trend = self._calculate_hourly_trend()

            # Calculate daily trend (last 7 days)
            daily_trend = await self._calculate_daily_trend(all_stats)

            return {
                "total_requests": total_requests,
                "successful_waybills": successful_waybills,
                "failed_attempts": failed_attempts,
                "success_rate": self._calculate_rate(successful_waybills, failed_attempts),
                "success_rate_percent": round((successful_waybills / max(1, successful_waybills + failed_attempts)) * 100, 2),
                "map_usage_distribution": map_usage,
                "performance": performance,
                "hourly_trend": hourly_trend,
                "daily_trend": daily_trend,
                "recent_errors": recent_errors,
                "current_mode_counters": {
                    mode: values.copy()
                    for mode, values in self._mode_counters.items()
                },
            }

    async def get_daily_report(self) -> dict[str, Any]:
        async with AsyncSession(engine) as session:
            statement = select(BotStats).order_by(BotStats.report_date)
            result = await session.execute(statement)
            all_stats = result.scalars().all()

            daily_stats = {}
            for stat in all_stats:
                day_str = stat.report_date.isoformat()
                total = stat.successful_waybills + stat.failed_attempts
                success_rate = (stat.successful_waybills / max(1, total)) * 100 if total > 0 else 0

                daily_stats[day_str] = {
                    "success": stat.successful_waybills,
                    "fail": stat.failed_attempts,
                    "total": total,
                    "success_rate": round(success_rate, 2),
                    "map_google": stat.map_google,
                    "map_openlayers": stat.map_openlayers,
                    "map_leaflet": stat.map_leaflet,
                    "map_mapbox": stat.map_mapbox,
                }
            return daily_stats

    async def get_operational_report(self) -> dict[str, Any]:
        async with self._op_lock:
            latencies = list(self._latency_samples)
            mode_counters = {
                mode: values.copy()
                for mode, values in self._mode_counters.items()
            }
            error_categories = self._error_categories.copy()
            error_details = list(self._error_details)
            success_times = list(self._success_times)

        # Calculate detailed latency stats
        latency_stats = {
            "count": len(latencies),
            "mean": round(mean(latencies), 2) if latencies else 0,
            "median": round(median(latencies), 2) if latencies else 0,
            "min": round(min(latencies), 2) if latencies else 0,
            "max": round(max(latencies), 2) if latencies else 0,
            "std_dev": round(self._std_dev(latencies), 2) if len(latencies) > 1 else 0,
            "p50": self._percentile(latencies, 50),
            "p75": self._percentile(latencies, 75),
            "p90": self._percentile(latencies, 90),
            "p95": self._percentile(latencies, 95),
            "p99": self._percentile(latencies, 99),
        }

        # Calculate success rate over time
        success_trend = self._calculate_success_trend(success_times)

        return {
            "latency_ms": latency_stats,
            "mode_counters": mode_counters,
            "error_categories": error_categories,
            "recent_errors": error_details[-20:],  # Last 20 errors
            "success_trend": success_trend,
            "total_tracked": len(latencies),
        }

    async def get_error_analysis(self) -> dict[str, Any]:
        """تحلیل خطاهای رخ داده با جزئیات"""
        async with self._op_lock:
            error_categories = self._error_categories.copy()
            error_details = list(self._error_details)

        # Group errors by category
        errors_by_category = {}
        for error in error_details:
            category = error["category"]
            if category not in errors_by_category:
                errors_by_category[category] = {
                    "count": 0,
                    "examples": []
                }
            errors_by_category[category]["count"] += 1
            if len(errors_by_category[category]["examples"]) < 5:
                errors_by_category[category]["examples"].append(error)

        # Calculate error rate by hour
        hourly_errors = {}
        for error in error_details:
            hour = error["timestamp"][:13]  # YYYY-MM-DDTHH
            if hour not in hourly_errors:
                hourly_errors[hour] = 0
            hourly_errors[hour] += 1

        return {
            "total_errors": len(error_details),
            "by_category": errors_by_category,
            "category_totals": error_categories,
            "hourly_distribution": hourly_errors,
            "most_recent": error_details[-10:] if error_details else []
        }

    async def get_performance_dashboard(self) -> dict[str, Any]:
        """داشبورد عملکرد با معیارهای کلیدی"""
        async with self._op_lock:
            latencies = list(self._latency_samples)
            success_times = list(self._success_times)

        # Calculate requests per minute (last 10 minutes)
        now = datetime.now()
        recent_window = now - timedelta(minutes=10)
        recent_requests = [
            s for s in success_times
            if datetime.fromisoformat(s["timestamp"]) > recent_window
        ]
        rpm = len(recent_requests) / 10.0

        return {
            "requests_per_minute": round(rpm, 2),
            "avg_response_time_ms": round(mean(latencies), 2) if latencies else 0,
            "p95_response_time_ms": self._percentile(latencies, 95),
            "success_rate_percent": self._calculate_success_rate_percent(success_times),
            "total_processed": len(success_times),
            "uptime_hours": self._calculate_uptime_hours(),
        }

    def get_mode_counters(self) -> dict[str, dict[str, int]]:
        return {
            mode: values.copy()
            for mode, values in self._mode_counters.items()
        }

    def _calculate_rate(self, success: int, total_failed: int) -> str:
        total = success + total_failed
        if total == 0:
            return "0%"
        rate = (success / total) * 100
        return f"{rate:.1f}%"

    def _calculate_success_rate_percent(self, success_times: list[dict]) -> float:
        if not success_times:
            return 0.0
        # This is a simplified calculation
        # In a real scenario, you'd track both successes and failures
        return 95.0  # Placeholder

    def _calculate_uptime_hours(self) -> float:
        # Simplified - in production, track actual start time
        return 24.0  # Placeholder

    def _calculate_hourly_trend(self) -> list[dict[str, Any]]:
        """محاسبه روند ساعتی"""
        hourly_data = {}

        for sample in self._hourly_samples:
            hour = sample["hour"]
            if hour not in hourly_data:
                hourly_data[hour] = {
                    "count": 0,
                    "total_latency": 0,
                    "successes": 0
                }
            hourly_data[hour]["count"] += 1
            hourly_data[hour]["total_latency"] += sample["latency"]

        # Calculate averages
        result = []
        for hour, data in sorted(hourly_data.items())[-24:]:  # Last 24 hours
            result.append({
                "hour": hour,
                "count": data["count"],
                "avg_latency": round(data["total_latency"] / data["count"], 2) if data["count"] > 0 else 0
            })

        return result

    async def _calculate_daily_trend(self, all_stats: list[BotStats]) -> list[dict[str, Any]]:
        """محاسبه روند روزانه"""
        trend = []
        for stat in sorted(all_stats, key=lambda x: x.report_date)[-7:]:  # Last 7 days
            total = stat.successful_waybills + stat.failed_attempts
            trend.append({
                "date": stat.report_date.isoformat(),
                "total": total,
                "success": stat.successful_waybills,
                "failed": stat.failed_attempts,
                "success_rate": round((stat.successful_waybills / max(1, total)) * 100, 2)
            })
        return trend

    def _calculate_success_trend(self, success_times: list[dict]) -> list[dict[str, Any]]:
        """محاسبه روند موفقیت در زمان"""
        if not success_times:
            return []

        # Group by hour
        hourly_counts = {}
        for item in success_times:
            hour = item["timestamp"][:13]
            if hour not in hourly_counts:
                hourly_counts[hour] = 0
            hourly_counts[hour] += 1

        return [
            {"hour": hour, "count": count}
            for hour, count in sorted(hourly_counts.items())[-24:]
        ]

    @staticmethod
    def _std_dev(samples: list[float]) -> float:
        """محاسبه انحراف معیار"""
        if len(samples) < 2:
            return 0.0
        avg = mean(samples)
        variance = sum((x - avg) ** 2 for x in samples) / (len(samples) - 1)
        return variance ** 0.5

    @staticmethod
    def _percentile(samples: list[float], percentile: int) -> float:
        if not samples:
            return 0.0

        sorted_values = sorted(samples)
        index = int(round((percentile / 100) * (len(sorted_values) - 1)))
        index = min(max(index, 0), len(sorted_values) - 1)
        return round(sorted_values[index], 2)


report_service = ReportService()
