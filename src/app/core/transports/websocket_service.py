from typing import Any

from fastapi import WebSocket
from loguru import logger
from pipecat.pipeline.task import PipelineParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
)

from app.agents import BaseAgent
from app.services.audio import create_krisp_viva_filter
from app.services.turn.turn_service import create_turn_analyzer
from app.services.vad import create_vad_analyzer
from app.db.database import get_database, MongoClient
from app.managers.session_manager import SessionManager

from .base_transport_service import run_pipeline
from .custom_websocket_transport import CustomFastAPIWebsocketTransport


async def run_websocket_bot(websocket: WebSocket, session_id: str, tenant_id: str, agent: BaseAgent, headers: dict[str, Any] | None = None):
    logger.info("Starting WebSocket bot")

    metadata = {
        "session_id": session_id,
        "assistant_id": websocket.query_params.get("assistant_id"),
        "assistant_overrides_id": websocket.query_params.get("assistant_overrides_id"),
        "headers": headers or {},
    }

    # Create Smart Turn analyzer and VAD analyzer from agent configuration
    turn_analyzer = create_turn_analyzer(agent.config.smart_turn)
    vad_analyzer = create_vad_analyzer(agent.config.vad, enable_turn_detection=bool(turn_analyzer))

    # Create Krisp VIVA noise suppression filter from agent configuration
    krisp_filter = create_krisp_viva_filter(agent.config.krisp_viva_filter)

    # Log which filter is being used
    if krisp_filter:
        filter_type = type(krisp_filter).__name__
        logger.info(f"🎤 Using audio filter: {filter_type} for WebSocket transport (16kHz)")
    else:
        logger.info("🎤 No audio filter configured for WebSocket transport")

    transport = CustomFastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=True,  # Add WAV header for browser-based clients
            audio_in_filter=krisp_filter,
            vad_analyzer=vad_analyzer,
            turn_analyzer=turn_analyzer,
        ),
    )

    pipeline_params = PipelineParams(
        audio_in_sample_rate=16000,  # Higher sample rate for web clients
        audio_out_sample_rate=16000,
        enable_metrics=True,
        enable_usage_metrics=True,
        report_only_initial_ttfb=agent.config.report_only_initial_ttfb,
    )

    await run_pipeline(transport=transport, agent=agent, session_id=session_id, tenant_id=tenant_id, provider_session_id=session_id, transport_name="websocket", pipeline_params=pipeline_params, metadata=metadata)


async def websocket_endpoint(websocket: WebSocket, session_id: str, tenant_id: str):
    logger.info(f"WebSocket connection received for session: {session_id}")

    client = MongoClient.get_client()
    db = get_database(tenant_id, client)
    session_manager = SessionManager(db)
    session = await session_manager.get_session(session_id)
    user_details_dict = session.created_by.model_dump() if session.created_by else None

    agent_config = await session_manager.get_and_consume_config(session_id=session_id, transport_name="websocket", provider_session_id=session_id)
    if not agent_config:
        logger.error(f"No session data or config found for session_id: {session_id}")
        await websocket.close()
        return

    logger.info(f"WebSocket connection accepted for session: {session_id}")
    agent = BaseAgent(agent_config=agent_config)
    headers = dict(websocket.headers)
    await agent.set_session_context(
        session_id=session.session_id,
        transport_name="websocket",
        db=db,
        tenant_id=tenant_id,
        provider_session_id=session_id,
        transport_metadata={"headers": headers},
        user_details=user_details_dict,
        call_data=None,
    )
    await run_websocket_bot(websocket, session_id, tenant_id, agent, headers=headers)
