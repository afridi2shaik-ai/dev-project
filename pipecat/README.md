## Pipecat Service

FastAPI-based voice AI server that wires together Pipecat components (WebRTC transport, VAD, STT, LLM, TTS) and telephony via Twilio. A small prebuilt WebRTC UI is mounted at `/client` for quick testing.

### Features
- WebRTC client at `/client` using `SmallWebRTCPrebuiltUI`
- Real-time pipeline: Silero VAD → OpenAI STT → OpenAI LLM (with context) → Sarvam TTS (ElevenLabs available)
- Twilio media streaming integration (inbound and outbound)
- **Custom API Tools & Database Integration** with advanced field validation and OAuth2 support
- **Centralized Engaging Words System** for consistent, action-oriented user feedback
- **Multi-language TTS routing** with automatic language detection
- Structured logging with Loguru; optional OpenTelemetry tracing

### Requirements
- Python 3.12+ (local)
- `uv` (recommended) or `pip`
- API keys and credentials in environment (see below)

### Configuration (environment variables)
Create a `.env` at the project root or export these variables:

- OPENAI_API_KEY: OpenAI API key
- SARVAM_API_KEY: Sarvam TTS API key
- ELEVENLABS_API_KEY: (optional) ElevenLabs TTS
- DEEPGRAM_API_KEY: (optional) if you add Deepgram
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER: Twilio telephony
- OTEL_EXPORTER_OTLP_ENDPOINT: (optional) OTLP endpoint (e.g., `http://collector:4317`)
- OTEL_DEBUG_LOG_SPANS: (optional, `true`/`false`) to log spans to console

Server settings (via `.env`, defaults shown):
- API_HOST: `0.0.0.0`
- API_PORT: `7860`
- ALLOWED_ORIGINS: `http://localhost:7860,http://localhost:8000`

### Install and run (local)
Using `uv`:

```bash
uv sync

# Development 
uv run dev

# Production
uv run prod

# Alternatively with uvicorn directly
uv run uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 7860 --reload
```

Then open `http://localhost:7860/client`.

### Run with Docker
This repo contains a `Dockerfile`. Build and run:

```bash
docker build -t pipecat-service .
docker run --rm -p 7860:7860 --env-file .env pipecat-service
```

Notes:
- The app defaults to port `7860`. If you keep the provided Dockerfile, update the port mapping to `-p 7860:7860`.
- The Dockerfile currently uses `python:3.11-slim` while the project requires `>=3.12`. To align versions, change the first line to:

```dockerfile
FROM python:3.12-slim
```

And consider updating the exposed port to match the app:

```dockerfile
EXPOSE 7860
```

### Endpoints
- Web UI: `GET /client`
- OpenAPI docs UI: `GET /docs` (renders `stoplight_elements.html` against `/openapi.json`)

#### Core Voice AI Endpoints
- WebRTC signaling (Pipecat):
  - `POST /api/offer` with JSON body:

```json
{
  "pc_id": null,
  "sdp": "<offer_sdp>",
  "type": "offer",
  "restart_pc": false
}
```

Returns:

```json
{
  "pc_id": "<server-pc-id>",
  "sdp": "<answer_sdp>",
  "type": "answer"
}
```

- Twilio telephony:
  - `POST /api/twilio/inbound`: Returns TwiML with `<Stream>` pointing to `wss://<host>/api/twilio/voice`
  - `WEBSOCKET /api/twilio/voice`: Twilio Media Streams connect here (handled internally)
  - `POST /api/twilio/outbound-call` with JSON body:

```json
{ "to": "+1XXXXXXXXXX" }
```

For inbound calls, set your Twilio Voice webhook URL to `https://<your-host>/api/twilio/inbound`. For local development, use a tunnel (e.g., ngrok) to expose your machine over HTTPS and update the webhook accordingly.

#### Custom API Tools & Database Integration
- **Custom Tools Management**:
  - `GET /api/tools` - List all custom API tools
  - `POST /api/tools` - Create new custom API tool
  - `GET /api/tools/{tool_id}` - Get tool details
  - `PUT /api/tools/{tool_id}` - Update tool configuration
  - `DELETE /api/tools/{tool_id}` - Delete tool
  - `POST /api/tools/{tool_id}/test` - Test tool with sample data


- **Advanced Features**:
  - **OAuth2 Authentication**: Support for client credentials and authorization code flows
  - **Field Validation**: Email, phone number, URL, date, and datetime validation
  - **Engaging Words System**: Contextual, action-oriented phrases for better UX
  - **Multi-TTS Language Routing**: Automatic language detection with appropriate TTS service

### Architecture overview
- `src/app/main.py`: FastAPI app, mounts UI at `/client`, includes routers under `/api`
- `src/app/api/`: route modules
  - `pipecat_api.py`: WebRTC offer/answer
  - `twilio_api.py`: Twilio inbound/outbound + WebSocket handler
  - `tools_api.py`: Custom API tools management and testing
- `src/app/services/`: pipeline building blocks
  - `pipecat_service.py`: Browser WebRTC transport pipeline
  - `twilio_service.py`: Twilio transport pipeline (8 kHz audio in/out)
  - `tool_registration_service.py`: Dynamic tool registration and LLM integration
  - `stt/`, `llm/`, `tts/`: service factories (OpenAI STT/LLM; Sarvam and ElevenLabs TTS)
- `src/app/tools/`: domain layer business logic
  - `custom_api_tool.py`: Advanced custom API integration with OAuth2 and validation
  - `engaging_words_config.py`: Centralized configuration for engaging phrases
  - `hangup_tool.py`: Call termination functionality
- `src/app/processors/`: custom pipeline processors
  - `multi_tts_router.py`: Language-aware TTS routing
  - `filler_words_processor.py`: LLM delay handling
- `src/app/core/`: settings, logging, tracing
- `src/app/templates/`: TwiML and docs page template

### Development tips
- The backend expects the `src` directory on `PYTHONPATH`. `uv run` and the provided commands handle this. If running plain Python, do:

```bash
PYTHONPATH=src uv run python -m app.main
```

- Logs include optional OpenTelemetry trace/span IDs if tracing is configured.

### Troubleshooting
- Python version inside Docker: if install fails due to `Requires-Python >=3.12`, switch the base image to `python:3.12-slim`.
- Port exposure: ensure you publish `-p 7860:7860` (or set `API_PORT` to `8000` if you prefer the Dockerfile’s current `EXPOSE 8000`).
- Credentials: missing keys (OpenAI/Sarvam/Twilio) will result in failures to start or to process calls; check logs.


### Local testing with ngrok
Expose your local server over HTTPS so Twilio can reach it.

1) Start the dev server

```bash
uv run dev
```

2) Start ngrok on the same port (default 7860)

```bash
ngrok http 7860
```

Copy the HTTPS forwarding URL shown by ngrok, for example: `https://abcd-1234.ngrok-free.app`.

3) Configure your Twilio Voice webhook to point to your inbound endpoint

- In the Twilio Console: Phone Numbers → Manage → Active Numbers → select your number → Voice & Fax → A Call Comes In → set to
  `https://<your-ngrok-host>/api/twilio/inbound` with method `POST`.

- Or via Twilio CLI:

```bash
twilio api:core:incoming-phone-numbers:update \
  --sid PNXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX \
  --voice-url https://<your-ngrok-host>/api/twilio/inbound \
  --voice-method POST
```

4) Test

- Call your Twilio number and watch your server logs. The app will return TwiML that instructs Twilio to open a WebSocket to
  `wss://<your-ngrok-host>/api/twilio/voice` automatically.

Notes
- Ensure your `.env` includes valid `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER`.
- ngrok supports WebSocket tunneling, so the `wss://` connection used by Twilio will work through the same host.
- If running in Docker, map the app port (e.g., `-p 7860:7860`) and run `ngrok http 7860` on the host.


