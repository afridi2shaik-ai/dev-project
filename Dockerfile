# Use an official Python runtime as a parent image
FROM python:3.12

# Set environment variables for best practices in containers
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# OpenTelemetry configuration
ENV OTEL_EXPORTER_OTLP_ENDPOINT=https://otelaivoice.cloudbuilders.io:4317 \
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc \
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=grpc \
    OTEL_PYTHON_LOG_LEVEL=debug \
    OTEL_LOG_LEVEL=debug \
    OTEL_EXPORTER_OTLP_INSECURE=true \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=otlp \
    OTEL_LOGS_EXPORTER=none

# Install system dependencies required by OpenCV, media handling, and Krisp build
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends --allow-downgrades \
       libgl1 \
       libglib2.0-0 \
       imagemagick \
       cmake \
       pybind11-dev \
       patchelf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv, a fast Python package installer
RUN pip install --no-cache-dir uv

# Install OpenTelemetry instrumentation tools
RUN uv pip install --no-cache-dir --system \
    opentelemetry-distro \
    opentelemetry-exporter-otlp-proto-grpc \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-instrumentation-requests \
    opentelemetry-instrumentation-urllib3

# Set the working directory in the container
WORKDIR /app

# Copy the Krisp wheel
COPY Krisp/krisp-audio-sdk-python-1.4.0/dist/krisp_audio-1.4.0-cp312-cp312-linux_x86_64.whl /wheels/

# Install the Krisp wheel explicitly
RUN uv pip install --no-cache-dir --system /wheels/krisp_audio-1.4.0-cp312-cp312-linux_x86_64.whl

# Fix the executable stack issue for libkrisp-audio-sdk.so
RUN find /usr/local/lib -name "libkrisp-audio-sdk.so*" -exec patchelf --clear-execstack {} \; || true

# Copy the application code into the container
COPY . /app/

# Install dependencies using the pyproject.toml and uv.lock for speed and determinism
RUN uv pip install --no-cache-dir --system .

# Expose the port the app runs on
EXPOSE 7860

# Run the application using the entry script defined in pyproject.toml
CMD ["opentelemetry-instrument", "prod"]
