from fastapi import APIRouter

from .artifact_api import artifact_router
from .assistant_api import assistant_router
from .auth import auth_router
from .business_tools.router import business_tools_router
from .dummy import dummy_router
from .customer_profile_api import router as customer_profile_router
from .log_api import log_router
from .pipecat_api import pipecat_router
from .plivo_api import plivo_router
from .session_api import session_router
from .token_api import token_router
from .chat_api import text_router
from .voice_to_chat_api import voice_to_chat_router

# Legacy tools_api removed - use business_tools instead
from .twilio_api import twilio_router
from .websocket_api import websocket_router

api_router = APIRouter()

api_router.include_router(pipecat_router, tags=["WebRTC"])
api_router.include_router(plivo_router, prefix="/plivo", tags=["Plivo"])
api_router.include_router(twilio_router, prefix="/twilio", tags=["Twilio"])
api_router.include_router(websocket_router, prefix="/websocket", tags=["WebSocket"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(assistant_router, prefix="/assistants", tags=["Assistants"])
api_router.include_router(customer_profile_router, prefix="/customer-profiles", tags=["Customer Profiles"])
api_router.include_router(session_router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(log_router, prefix="/logs", tags=["Logs"])
api_router.include_router(artifact_router, prefix="/artifacts", tags=["Artifacts"])
api_router.include_router(business_tools_router, prefix="/business-tools", tags=["Business Tools"])
api_router.include_router(token_router, prefix="/credentials", tags=["API Credentials"])
api_router.include_router(dummy_router, prefix="/dummy", tags=["Dummy"])
api_router.include_router(text_router, prefix="/text", tags=["Text"])
api_router.include_router(voice_to_chat_router, tags=["Voice-to-Chat"])