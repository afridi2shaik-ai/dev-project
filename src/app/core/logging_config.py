import json
import logging
import sys

from loguru import logger
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from .config import LogLevel, settings


class InterceptHandler(logging.Handler):
    """
    Intercepts standard logging messages and redirects them to Loguru.
    This handler is part of the setup to make Loguru the primary logger.
    """

    def emit(self, record: logging.LogRecord):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 0
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def trace_context_processor(record):
    """
    Loguru processor to add OpenTelemetry trace and span IDs to the log record.
    """
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        ctx = span.get_span_context()
        record["extra"]["trace_id"] = f"{ctx.trace_id:032x}"
        record["extra"]["span_id"] = f"{ctx.span_id:016x}"
    else:
        # Use setdefault to avoid KeyError in format string if keys don't exist
        record["extra"].setdefault("trace_id", "N/A")
        record["extra"].setdefault("span_id", "N/A")


def configure_logging(log_level: LogLevel | None = None):
    """
    Configures the Loguru logger to be the primary logger for the application,
    intercepting standard library logging calls, and enriching logs with
    OpenTelemetry trace context.
    """
    level = log_level or settings.LOG_LEVEL

    # Remove any default handlers and reconfigure
    logger.remove()

    # Add processor for OpenTelemetry context first to ensure it's always available
    logger.configure(patcher=trace_context_processor)

    logger.add(
        sys.stderr,
        level=level.upper(),
        format=("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <yellow>trace_id={extra[trace_id]}</yellow> | <yellow>span_id={extra[span_id]}</yellow> | <level>{message}</level>"),
        colorize=True,
        serialize=settings.LOGURU_JSON_LOGS,
    )

    # Intercept standard logging messages toward your configured loguru sinks
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Configure OpenTelemetry Log Exporter
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        log_provider = LoggerProvider()
        set_logger_provider(log_provider)

        exporter = OTLPLogExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
        log_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

        # This handler will be used by our custom sink to push logs to OTel.
        otel_handler = LoggingHandler(level=logging.getLevelName(level.upper()), logger_provider=log_provider)

        def otel_sink(message):
            """A Loguru sink that sends serialized records to OpenTelemetry."""
            try:
                record_data = json.loads(message)
                record = record_data.get("record", {})

                log_record = logging.LogRecord(name=record.get("name"), level=record.get("level", {}).get("no", logging.INFO), pathname=record.get("file", {}).get("path"), lineno=record.get("line"), msg=record.get("message"), args=(), exc_info=record.get("exception"), func=record.get("function"))
                otel_handler.emit(log_record)
            except Exception as e:
                # Fallback to prevent logger from crashing application
                logger.warning(f"Error sending log to OTel: {e}")

        # Add the sink to Loguru. All logs will now go to console and OTel.
        logger.add(otel_sink, serialize=True, level=level.upper())
        logger.info(f"OpenTelemetry logging configured to export to {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")

    logger.info(f"Logging configured successfully with level {level}.")
