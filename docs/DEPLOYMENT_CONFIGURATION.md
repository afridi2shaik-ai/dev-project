# Deployment & Configuration Guide

## Overview

This guide covers environment configuration, server setup, Docker deployment, performance tuning, and production best practices.

## Table of Contents

1. [Environment Configuration](#environment-configuration)
2. [Server Setup](#server-setup)
3. [Docker Deployment](#docker-deployment)
4. [Performance Tuning](#performance-tuning)
5. [Production Checklist](#production-checklist)

---

## Environment Configuration

### Core Settings

**File:** `src/app/core/config.py`

**Critical Variables:**

```bash
# Application
APP_NAME=Pipecat-Service
AGENT_TYPE=vagent_pipe_cat
LOG_LEVEL=INFO

# Server
API_HOST=0.0.0.0
API_PORT=7860

# CORS
ALLOWED_ORIGINS=http://localhost:8000,https://yourdomain.com

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_DEFAULT=pipecat
```

### Authentication (Auth0)

```bash
# Enable/disable
AUTH_ENABLED=true

# Auth0
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_API_IDENTIFIER=https://your-api
AUTH0_M2M_CLIENT_ID=your-m2m-client-id
AUTH0_M2M_CLIENT_SECRET=your-m2m-secret

# Token generation
AUTH_USERNAME=admin@example.com
AUTH_PASSWORD=admin_password
```

### LLM Providers

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Google Gemini
GEMINI_API_KEY=...
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# Others
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
SARVAM_API_KEY=...
CARTESIA_API_KEY=...
```

### Telephony

```bash
# Plivo
PLIVO_AUTH_ID=...
PLIVO_AUTH_TOKEN=...
PLIVO_PHONE_NUMBER=+1-xxx-xxxx

# Twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1-xxx-xxxx
```

### Audio Processing

```bash
# Krisp (noise reduction)
KRISP_SDK_WHEEL_PATH=/path/to/krisp.whl
KRISP_VIVA_MODEL_PATH=Krisp/krisp-viva-models-9.9/krisp-viva-pro-v1.kef
```

### AWS S3

```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=pipecat-logs
```

### OpenTelemetry

```bash
OTEL_SERVICE_NAME=pipecat-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_DEBUG_LOG_SPANS=false
```

### Configuration Class

**Access in code:**
```python
from app.core import settings

print(f"App Name: {settings.APP_NAME}")
print(f"API Port: {settings.API_PORT}")
print(f"Auth Enabled: {settings.AUTH_ENABLED}")
```

---

## Server Setup

### Prerequisites

```bash
Python 3.11+
MongoDB 4.4+
Docker & Docker Compose (optional)
```

### Installation

```bash
# Clone repository
git clone <repo-url>
cd pipecat-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration
```

### Start Server

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 7860

# Production
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:7860
```

### Verify

```bash
# Health check
curl http://localhost:7860/health

# API docs
open http://localhost:7860/docs
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 7860

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "7860:7860"
    environment:
      - MONGODB_URI=mongodb://mongo:27017
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - AUTH_ENABLED=${AUTH_ENABLED}
      - AUTH0_DOMAIN=${AUTH0_DOMAIN}
    depends_on:
      - mongo
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  mongo:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    restart: unless-stopped

volumes:
  mongo_data:
```

**Start:**
```bash
docker-compose up -d
```

---

## Performance Tuning

### 1. Database Optimization

**Indexes:**
```python
# Create indexes in MongoDB
db.sessions.create_index([("tenant_id", 1), ("created_at", -1)])
db.sessions.create_index([("state", 1)])
db.customer_profiles.create_index([("tenant_id", 1), ("phone", 1)])
```

**Connection Pool:**
```python
# In code
MONGODB_MAX_POOL_SIZE=50  # Default: 10
MONGODB_MIN_POOL_SIZE=10  # Default: 0
```

### 2. LLM Configuration

**Token optimization:**
```python
# Reduce tokens
max_tokens = 1024  # Instead of 4096
temperature = 0.7  # Faster than 1.5

# Limit history
max_messages = 50  # Prevent unbounded growth
```

### 3. Network Optimization

**Timeouts:**
```python
AIOHTTP_TIMEOUT=30  # Seconds
LLM_TIMEOUT=30  # Seconds
DATABASE_TIMEOUT=10  # Seconds
```

**Connection pooling:**
```python
# In main.py
app.state.http_client = aiohttp.ClientSession(
    connector=aiohttp.TCPConnector(limit_per_host=10)
)
```

### 4. Memory Optimization

**Pipeline tuning:**
```python
# Limit audio buffer
audio_buffer_size = 10_000  # Frames

# Limit message queue
max_queue_size = 1000  # Frames

# Reduce processor overhead
disable_unused_processors = True
```

### 5. Concurrency

**Workers:**
```bash
# Production: use multiple workers
gunicorn --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Each worker handles multiple sessions
# CPU count typically = optimal workers
```

**Async efficiency:**
```python
# Use asyncio properly
async def process_batch():
    tasks = [process_item(i) for i in items]
    await asyncio.gather(*tasks)  # Parallel execution
```

---

## Production Checklist

### Pre-Deployment

- [ ] All tests passing (`pytest`)
- [ ] Linting passes (`flake8`, `mypy`)
- [ ] Environment variables configured
- [ ] API keys secured (not in code)
- [ ] CORS origins restricted (not `*`)
- [ ] Auth enabled (if customer-facing)
- [ ] HTTPS certificate ready
- [ ] Database backups configured
- [ ] Logging configured
- [ ] Monitoring setup

### Deployment

- [ ] Deploy to staging first
- [ ] Run smoke tests
- [ ] Verify all API endpoints
- [ ] Test auth flow
- [ ] Test external integrations
- [ ] Verify database connectivity
- [ ] Check logs for errors
- [ ] Load test (at least 100 concurrent)

### Post-Deployment

- [ ] Monitor error rates
- [ ] Track response times
- [ ] Monitor resource usage (CPU, memory)
- [ ] Verify log aggregation
- [ ] Test failover procedures
- [ ] Document any issues
- [ ] Schedule incident post-mortem if needed

### Security

- [ ] SSL/TLS enabled (HTTPS only)
- [ ] API keys rotated
- [ ] Database credentials secure
- [ ] Network policies restrictive
- [ ] Rate limiting enabled
- [ ] Input validation strict
- [ ] Error messages don't leak info
- [ ] Audit logging enabled

### Scaling

- [ ] Load balancer configured
- [ ] Multiple instances running
- [ ] Database read replicas (if needed)
- [ ] CDN for static files (if applicable)
- [ ] Cache layer (Redis) configured
- [ ] Auto-scaling policies set

---

## Quick Start Commands

```bash
# Development
make dev          # Start with hot reload

# Production
make build        # Build Docker image
make run          # Run Docker container
make logs         # View logs
make stop         # Stop container

# Testing
make test         # Run tests
make coverage     # Coverage report
make lint         # Run linter

# Database
make db-migrate   # Run migrations
make db-backup    # Backup database
make db-restore   # Restore from backup
```

---

## Summary

Key configuration areas:
- **Environment variables** - All settings via .env
- **Authentication** - Auth0 integration
- **API keys** - Secure storage practices
- **Database** - Connection optimization
- **Monitoring** - Health checks and metrics
- **Performance** - Tuning for production
- **Security** - HTTPS, auth, encryption

Follow the production checklist before each deployment to ensure reliability and security.

