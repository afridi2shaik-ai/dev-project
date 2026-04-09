from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from opentelemetry import trace
from app.services.auth_service import AuthService
from app.schemas.request_params import WebsocketVoiceParams
from app.core.transports.websocket_chat import websocket_text_endpoint


tracer = trace.get_tracer(__name__)

text_router = APIRouter()

@text_router.websocket("/chat/{session_id}")
async def text(websocket: WebSocket, session_id: str):
    with tracer.start_as_current_span("websocket_text_handler"):
        # await websocket.accept()
        try:
            # Extract tokens from subprotocols
            subprotocols = websocket.headers.get("Sec-WebSocket-Protocol")
            logger.info(f"Received subprotocols: {subprotocols}")
            if not subprotocols:
                await websocket.close(code=1008, reason="Missing subprotocols")
                return

            # Split subprotocols into access_token and id_token
            tokens = subprotocols.split(",")
            if len(tokens) < 1:
                await websocket.close(code=1008, reason="Missing tokens")
                return

            access_token = tokens[0].strip()
            id_token = tokens[1].strip() if len(tokens) > 1 else None

            # Decode the access_token to extract tenant_id
            decoded = AuthService.decode_jwt_token(access_token)
            tenant_id = decoded["tenant_id"]
           

            # Optionally decode the id_token if provided
            if id_token:
                AuthService.decode_id_token(id_token)
                
            selected_subprotocol = tokens[0]  # or choose another logic to select subprotocol

            # Accept WebSocket with the selected subprotocol
            await websocket.accept(subprotocol=selected_subprotocol)

            # Now proceed with your existing WebSocket logic
            await websocket_text_endpoint(websocket, session_id, tenant_id)

        except WebSocketDisconnect:
            logger.info("Text WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error in text WebSocket handler: {e}")
            await websocket.close()
