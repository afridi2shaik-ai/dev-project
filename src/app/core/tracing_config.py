from collections.abc import Sequence

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)

from .config import settings


class NullSpanExporter(SpanExporter):
    """A SpanExporter that does nothing, effectively silencing trace output."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def configure_tracing():
    """
    Configures OpenTelemetry for distributed tracing.

    Sets up a TracerProvider and a SpanProcessor with an exporter.
    - If OTEL_EXPORTER_OTLP_ENDPOINT is set, it uses the OTLP exporter.
    - Otherwise, it defaults to a ConsoleSpanExporter for local development.
    """
    # Check if a tracer provider is already set to prevent double initialization
    current_provider = trace.get_tracer_provider()
    if hasattr(current_provider, "__class__") and current_provider.__class__.__name__ == "TracerProvider":
        logger.debug("OpenTelemetry TracerProvider already configured, skipping re-initialization")
        return

    resource = Resource(attributes={"service.name": settings.OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    # Determine which exporter to use based on settings
    exporter: SpanExporter
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True, timeout=5)
        log_message = f"OpenTelemetry configured with OTLP exporter to {settings.OTEL_EXPORTER_OTLP_ENDPOINT}"
    elif settings.OTEL_DEBUG_LOG_SPANS:
        exporter = ConsoleSpanExporter()
        log_message = "OpenTelemetry configured with ConsoleSpanExporter. Traces will be printed to the console."
    else:
        exporter = NullSpanExporter()
        log_message = "OpenTelemetry tracing is active. Spans are not being exported to console."

    # Set up the processor and provider, then log the configuration status
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    logger.info(log_message)

    # You can get a tracer instance in other parts of your app like this:
    # tracer = trace.get_tracer(__name__)
