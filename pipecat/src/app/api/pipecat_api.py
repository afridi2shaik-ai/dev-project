from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry import trace

from app.agents import BaseAgent
from app.api.dependencies import get_db
from app.core.transports import webrtc_manager
from app.core.transports.webrtc_service import WebRTCService
from app.managers.session_manager import SessionManager
from app.schemas import OfferRequest, OfferResponse

tracer = trace.get_tracer(__name__)

pipecat_router = APIRouter()


@pipecat_router.post("/offer", response_model=OfferResponse)
async def offer(request: OfferRequest, background_tasks: BackgroundTasks, db: AsyncIOMotorDatabase = Depends(get_db)):
    with tracer.start_as_current_span("websocket_handler"):
        if not request.session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        pipecat_connection = await webrtc_manager.get_connection(request.pc_id)

        session_manager = SessionManager(db)
        agent_config = await session_manager.get_and_consume_config(session_id=request.session_id, transport_name="webrtc", provider_session_id=pipecat_connection.pc_id)
        if not agent_config:
            raise HTTPException(status_code=404, detail=f"Session data not found for session_id: {request.session_id}")

        if request.pc_id and request.pc_id in webrtc_manager._connections:
            await pipecat_connection.renegotiate(
                sdp=request.sdp,
                type=request.type,
                restart_pc=request.restart_pc,
            )
        else:
            await pipecat_connection.initialize(sdp=request.sdp, type=request.type)
            agent = BaseAgent(agent_config=agent_config)

            metadata = {
                "pc_id": pipecat_connection.pc_id,
                "session_id": request.session_id,
                "restart_pc": request.restart_pc,
            }

            tenant_id = db.name
            pipecat_service = WebRTCService(pipecat_connection, agent, tenant_id=tenant_id, metadata=metadata)
            background_tasks.add_task(pipecat_service.run_bot, False)

        answer = pipecat_connection.get_answer()
        webrtc_manager.add_connection(pipecat_connection)

        return OfferResponse(pc_id=answer["pc_id"], sdp=answer["sdp"], type=answer["type"], session_id=request.session_id)
