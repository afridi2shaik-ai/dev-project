# Debugging & Observability Guide

## Overview

This guide covers logging, tracing, monitoring, and troubleshooting techniques for the Pipecat-Service.

## Table of Contents

1. [Logging Configuration](#logging-configuration)
2. [Observability Features](#observability-features)
3. [OpenTelemetry Tracing](#opentelemetry-tracing)
4. [Common Issues](#common-issues)
5. [Debugging Tips](#debugging-tips)

---

## Logging Configuration

### Loguru Setup

**File:** `src/app/core/logging_config.py`

**Environment Variables:**
```bash
LOG_LEVEL=DEBUG          # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOGURU_JSON_LOGS=false   # Enable JSON logging for log aggregation
```

### Log Levels

```
DEBUG   - Detailed frame-by-frame processing
INFO    - Major events (session start/end, config loading)
WARNING - Recoverable issues (retry, fallback)
ERROR   - Failures that affect functionality
CRITICAL - System-level failures
```

### Enabling Debug Logging

```python
import logging
from loguru import logger

# In your code
logger.enable("app")  # Enable app module
logger.add(sys.stderr, level="DEBUG")
```

### Structured Logging

**Example:**
```python
logger.info(f"Session created", extra={
    "session_id": session_id,
    "assistant_id": assistant_id,
    "transport": transport,
})
```

---

## Observability Features

### Observers

**Purpose:** Monitor pipeline events and collect metrics

**Location:** `src/app/core/observers/`

**Key Observers:**

1. **SessionLogObserver** - Tracks session events
2. **SummarizationObserver** - Accumulates transcripts for summarization
3. **MetricsLogger** - Collects performance metrics
4. **HangupObserver** - Detects call termination

### Metrics Collection

**Built-in metrics:**
- Call duration
- Message count
- Token usage
- API latencies
- Error rates

**Access:**
```python
from app.core.observers.metrics_logger import get_metrics

metrics = get_metrics(session_id)
print(f"Call Duration: {metrics.duration_seconds}s")
print(f"Messages: {metrics.message_count}")
print(f"Tokens: {metrics.total_tokens}")
```

### Health Checks

**Endpoint:** `GET /health`

**Response:**
```json
{
    "status": "healthy",
    "uptime_seconds": 3600,
    "active_sessions": 5,
    "total_sessions": 150
}
```

---

## OpenTelemetry Tracing

### Configuration

**File:** `src/app/core/tracing_config.py`

**Environment Variables:**
```bash
OTEL_SERVICE_NAME=pipecat-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_DEBUG_LOG_SPANS=false
```

### Enable Tracing

```python
from app.core import configure_tracing

configure_tracing()  # Instruments FastAPI, aiohttp, etc.
```

### Trace Output

**Example trace structure:**
```
Session Init (100ms)
├─ Load Assistant Config (20ms)
├─ Build Pipeline (30ms)
├─ Initialize LLM (15ms)
└─ Start Agent (35ms)

User Message (500ms)
├─ STT (100ms)
├─ LLM Processing (300ms)
└─ TTS (100ms)

Session End (50ms)
├─ Finalize Transcript (20ms)
└─ Cleanup (30ms)
```

### Visualize Traces

**With Jaeger:**
```bash
# Start Jaeger locally
docker run --rm \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one

# View traces at http://localhost:16686
```

---

## Common Issues

### Issue: High Memory Usage

**Symptoms:** Memory grows continuously

**Diagnosis:**
```python
# Check message queue depth
logger.info(f"Processor queue: {processor._input_queue.qsize()}")

# Check buffer sizes
logger.info(f"Audio buffer size: {audio_buffer.get_size()}")
```

**Solutions:**
1. Limit message history in context
2. Reduce audio buffer size
3. Check for frame queue deadlock

### Issue: High Latency

**Symptoms:** Slow response times

**Diagnosis:**
```python
# Log processing times
import time

start = time.time()
await llm.process_frame(frame, direction)
elapsed = time.time() - start
logger.warning(f"LLM processing took {elapsed:.2f}s")
```

**Solutions:**
1. Use Deepgram for STT (faster)
2. Reduce LLM temperature/tokens
3. Use multimodal mode for ultra-low latency
4. Check network latency to external services

### Issue: STT Not Working

**Symptoms:** No transcriptions, empty messages

**Diagnosis:**
```python
# Check audio input
logger.debug(f"Audio frame size: {len(frame.audio)} bytes")
logger.debug(f"Sample rate: {frame.sample_rate} Hz")

# Check STT service
logger.info(f"STT service initialized: {stt_service}")
logger.debug(f"STT provider: {stt_service.__class__.__name__}")
```

**Solutions:**
1. Verify API key in environment
2. Check TranscriptionFilter isn't filtering all output
3. Verify sample rate is correct (typically 16000)
4. Check network connectivity to STT provider

### Issue: LLM Timeout

**Symptoms:** No response, timeout errors

**Diagnosis:**
```python
# Check message history size
logger.debug(f"Message count: {len(messages)}")
logger.debug(f"Total tokens (estimate): {sum(len(m.split()) for m in messages)}")

# Check LLM config
logger.debug(f"Model: {llm_config.model}")
logger.debug(f"Timeout: {llm_config.timeout_seconds}")
```

**Solutions:**
1. Limit message history with max_messages
2. Reduce max_tokens setting
3. Check LLM provider status/API health
4. Increase timeout value

### Issue: Session Not Created

**Symptoms:** Failed to create session

**Diagnosis:**
```python
# Check database
logger.error(f"DB available: {db is not None}")
logger.error(f"DB name: {db.name}")

# Check assistant config fetch
logger.debug(f"Assistant API URL: {ASSISTANT_API_URL}")
```

**Solutions:**
1. Verify MongoDB is running
2. Check assistant configuration exists
3. Verify API tokens are valid
4. Check network connectivity to assistant API

---

## Debugging Tips

### 1. Enable Frame Logging

Add custom processor to log all frames:

```python
class DebugFrameLogger(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        logger.debug(f"{type(frame).__name__} ({direction.name})")
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

# Add to pipeline
processors.insert(0, DebugFrameLogger())
```

### 2. Trace LLM Messages

```python
# Before LLM processing
logger.debug(f"LLM Messages: {json.dumps(messages, indent=2)}")

# After LLM response
logger.debug(f"LLM Response: {response}")
logger.debug(f"Tokens used: {response.usage}")
```

### 3. Monitor External API Calls

```python
import time

async def call_external_api(url, params):
    start = time.time()
    try:
        response = await aiohttp_session.post(url, json=params)
        elapsed = time.time() - start
        logger.info(f"API call took {elapsed:.2f}s, status {response.status}")
        return await response.json()
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"API call failed after {elapsed:.2f}s: {e}")
        raise
```

### 4. Test Individual Components

```python
# Test STT
async def test_stt():
    stt = create_stt_service()
    frame = AudioRawFrame(audio=test_audio, sample_rate=16000)
    result = await stt.process_frame(frame)
    logger.info(f"STT result: {result}")

# Test LLM
async def test_llm():
    llm = create_llm_service()
    frame = LLMTextFrame(text="Hello")
    result = await llm.process_frame(frame)
    logger.info(f"LLM result: {result}")
```

### 5. Session Replay

**Fetch session data:**
```python
session = await session_manager.get_session(session_id)
logs = await session_manager.get_session_logs(session_id)

# Inspect
print(f"State: {session.state}")
print(f"Duration: {session.end_time - session.created_at}")
print(f"Artifacts: {len(logs.artifacts)}")
```

---

## Monitoring in Production

### Key Metrics to Track

```python
metrics = {
    "call_duration_seconds": avg_call_duration,
    "success_rate": successful_calls / total_calls,
    "avg_first_response_ms": avg_time_to_first_response,
    "error_rate": errors / total_calls,
    "active_sessions": current_active_count,
    "api_latency_ms": avg_external_api_latency,
    "token_usage": total_tokens,
}
```

### Alert Thresholds

```
High Error Rate: > 5% errors
Slow Response: > 3000ms first response
Memory Leak: Steady growth without decrease
API Timeout: > 30s
Database Issue: Connection timeout
```

---

## Summary

Key debugging tools:
- **Loguru** - Structured logging
- **Observers** - Event tracking
- **OpenTelemetry** - Distributed tracing
- **Health checks** - System status
- **Frame logging** - Pipeline debugging
- **Metrics** - Performance tracking

Use these to identify, diagnose, and resolve issues in production.

