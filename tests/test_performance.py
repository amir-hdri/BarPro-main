"""Tests for performance monitoring utilities."""
import asyncio

import pytest

from app.core.performance import async_timer, measure_async_time, measure_time, performance_monitor, timer


class TestPerformance:
    """Test performance monitoring utilities."""

    def test_timer_context_manager(self):
        """Test timer context manager."""
        with timer("test_operation"):
            pass  # Should complete without error

    @pytest.mark.asyncio
    async def test_async_timer_context_manager(self):
        """Test async timer context manager."""
        async with async_timer("test_async_operation"):
            await asyncio.sleep(0.01)

    def test_measure_time_decorator(self):
        """Test measure_time decorator."""
        @measure_time
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"

    def test_measure_time_decorator_with_custom_name(self):
        """Test measure_time decorator with custom operation name."""
        @measure_time(operation_name="custom_operation")
        def test_func():
            return "result"

        result = test_func()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_measure_async_time_decorator(self):
        """Test measure_async_time decorator."""
        @measure_async_time
        async def test_async_func():
            await asyncio.sleep(0.01)
            return "result"

        result = await test_async_func()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_performance_monitor_record_metric(self):
        """Test performance monitor records metrics."""
        await performance_monitor.reset_metrics()

        await performance_monitor.record_metric("test_metric", 100.0)
        await performance_monitor.record_metric("test_metric", 200.0)

        metrics = await performance_monitor.get_metrics()
        assert "test_metric" in metrics
        assert metrics["test_metric"]["count"] == 2
        assert metrics["test_metric"]["avg"] == 150.0
        assert metrics["test_metric"]["min"] == 100.0
        assert metrics["test_metric"]["max"] == 200.0

    @pytest.mark.asyncio
    async def test_performance_monitor_reset(self):
        """Test performance monitor reset."""
        await performance_monitor.record_metric("test_metric", 100.0)
        await performance_monitor.reset_metrics()

        metrics = await performance_monitor.get_metrics()
        assert len(metrics) == 0
