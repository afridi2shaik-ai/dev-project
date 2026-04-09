from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.api.routes import api_router
from app.api.ui_api import ui_router
from app.core import configure_logging, configure_tracing, settings
from app.core.transports import webrtc_manager
from app.core.metrics import ACTIVE_CALLS
from app.schemas.session_schema import SessionState
from app.db.database import MongoClient


# Load environment variables from .env file
load_dotenv(override=True)
# configure_logging()
configure_tracing()

# Instrument aiohttp to automatically propagate trace context (prevent double instrumentation)
if not AioHttpClientInstrumentor()._is_instrumented_by_opentelemetry:
    AioHttpClientInstrumentor().instrument()

logger.info("Loading Silero VAD model...")
logger.info("✅ Silero VAD model loaded")
logger.info("Loading pipeline components...")
logger.info("✅ Pipeline components loaded")
logger.info("Loading WebRTC transport...")
logger.info("✅ All components loaded successfully!")

# Log critical Auth0 settings for debugging
if settings.AUTH_ENABLED:
    logger.info(f"Auth enabled. Domain: '{settings.AUTH0_DOMAIN}', API Identifier: '{settings.AUTH0_API_IDENTIFIER}'")
else:
    logger.warning("Auth is disabled. All requests will be unauthenticated.")

# Log S3 storage configuration
if settings.S3_BUCKET_NAME and not settings.SAVE_TO_LOCAL:
    logger.info(f"AWS S3 storage enabled. Bucket: '{settings.S3_BUCKET_NAME}', Region: '{settings.AWS_REGION}'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import aiohttp

    app.state.http_client = aiohttp.ClientSession()
    logger.info("Created shared HTTP client session")

    yield

    # Shutdown
    logger.info("Disconnecting all WebRTC connections...")
    await webrtc_manager.disconnect_all()
    logger.info("All WebRTC connections disconnected.")

    logger.info("Closing shared HTTP client session...")
    await app.state.http_client.close()
    logger.info("HTTP client session closed.")


app = FastAPI(
    title=settings.APP_NAME,
    description="A simple, elegant, and powerful voice AI server designed to be instantly deployable. This server-side application provides a robust foundation for building and scaling voice-based AI solutions, offering a streamlined setup for developers to integrate and manage voice functionalities.",
    version="1.0.0",
    contact={
        "name": "CloudBuilders VAgent"
    },
    openapi_tags=[
        {
            "name": "VAgent",
            "description": "Endpoints for handling VAgent voice AI interactions, including session management and real-time communication.",
        }
    ],
    lifespan=lifespan,
    openapi_url="/vagent/openapi.json",
    docs_url="/docs_v0",
    redoc_url=None,
)
print(settings.ALLOWED_ORIGINS)
# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument the FastAPI app (prevent double instrumentation)
if not hasattr(app, "_is_instrumented_by_opentelemetry") or not app._is_instrumented_by_opentelemetry:
    FastAPIInstrumentor.instrument_app(app)


# ---- Prometheus metrics endpoint ----
@app.get("/vagent/metrics")
async def metrics():
    client = MongoClient.get_client()
    total_active_sessions = 0

    # Only consider sessions updated in last 5 minutes
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    db_names = await client.list_database_names()

    for db_name in db_names:
        if db_name in ("admin", "config", "local"):
            continue

        if db_name == settings.MONGO_GLOBAL_DB:
            continue

        db = client[db_name]
        collection = db["sessions"]

        active_count = await collection.count_documents({
            "agent_type": settings.AGENT_TYPE,
            "state": {
                "$in": [
                    SessionState.PREFLIGHT.value,
                    SessionState.IN_FLIGHT.value
                ]
            },
            "updated_at": {"$gte": cutoff_time}
        })

        total_active_sessions += active_count

    # Set metric to real DB value
    ACTIVE_CALLS.set(total_active_sessions)

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)



# app.mount("/client", SmallWebRTCPrebuiltUI)
app.include_router(api_router, prefix="/vagent/api")
app.include_router(ui_router, prefix="/vagent")


def run_dev_server():
    logger.info("Starting development server...")
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        # reload=True,
        # log_config=None,
    )


def run_server():
    logger.info("Starting prod server...")
    configure_logging()
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
        # log_config=None,
    )
