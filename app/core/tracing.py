"""OpenTelemetry tracing configuration for UTCMS automation."""

import logging
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, Status, StatusCode

from app.core.config import utcms_config
from app.core.execution_context import get_execution_context

logger = logging.getLogger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None


def setup_tracing(service_name: str = "utcms-automation") -> None:
    """Initialize OpenTelemetry tracing."""
    global _tracer_provider, _tracer

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": "production" if utcms_config.ALLOW_LIVE_SUBMIT else "development",
        }
    )

    _tracer_provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint configured
    otlp_endpoint = getattr(utcms_config, "OTLP_ENDPOINT", None)
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        _tracer_provider.add_span_processor(span_processor)
        logger.info("otlp_tracing_enabled", extra={"extra_fields": {"endpoint": otlp_endpoint}})

    # Add console exporter in development
    if utcms_config.LOG_LEVEL == "DEBUG":
        console_exporter = ConsoleSpanExporter()
        console_processor = BatchSpanProcessor(console_exporter)
        _tracer_provider.add_span_processor(console_processor)

    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer(__name__)
    logger.info("tracing_initialized")


def get_tracer() -> trace.Tracer:
    """Get the configured tracer."""
    if _tracer is None:
        setup_tracing()
    return _tracer


@contextmanager
def trace_span(name: str, **attributes):
    """Context manager for tracing a span with attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        execution_context = get_execution_context()
        span.set_attribute("correlation_id", execution_context.correlation_id)
        span.set_attribute("task_id", execution_context.task_id)
        span.set_attribute("batch_id", execution_context.batch_id)
        span.set_attribute("worker_id", execution_context.worker_id)
        for key, value in attributes.items():
            span.set_attribute(key, str(value))
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        else:
            span.set_status(Status(StatusCode.OK))


def record_span_error(span: Span, error: Exception) -> None:
    """Record an error on a span."""
    span.set_status(Status(StatusCode.ERROR, str(error)))
    span.record_exception(error)


def get_current_span() -> Optional[Span]:
    """Get the current active span."""
    return trace.get_current_span()


def shutdown_tracing() -> None:
    """Shutdown tracing and flush pending spans."""
    global _tracer_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
        _tracer_provider = None
