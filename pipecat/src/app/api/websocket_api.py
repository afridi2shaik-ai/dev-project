from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from loguru import logger
from openai import BaseModel
from opentelemetry import trace

from app.core.transports.websocket_service import websocket_endpoint
from app.schemas.request_params import WebsocketVoiceParams


tracer = trace.get_tracer(__name__)
websocket_router = APIRouter()


@websocket_router.websocket("/voice/{session_id}")
async def voice(websocket: WebSocket, params: WebsocketVoiceParams = Depends()):
    with tracer.start_as_current_span("websocket_handler"):
        await websocket.accept()
        try:
            tenant_id = websocket.query_params.get("tenant_id")
            if not params.session_id or not tenant_id:
                logger.error("session_id and tenant_id are required in WebSocket URL")
                await websocket.close(code=1008)
                return

            await websocket_endpoint(websocket, params.session_id, tenant_id)

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}")
            await websocket.close()
            