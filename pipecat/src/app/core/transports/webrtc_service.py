from typing import Any

from loguru import logger
from pipecat.pipeline.task import PipelineParams
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCConnection, SmallWebRTCTransport

from app.agents import BaseAgent
from app.services.audio import create_krisp_viva_filter
from app.services.turn.turn_service import create_turn_analyzer
from app.services.vad import create_vad_analyzer
from app.db.database import MongoClient, get_database
from app.managers.session_manager import SessionManager

from .base_transport_service import run_pipeline


class WebRTCService:
    def __init__(self, webrtc_connection: SmallWebRTCConnection, agent: BaseAgent, tenant_id: str, metadata: dict[str, Any] | None = None):
        self._webrtc_connection = webrtc_connection
        self._agent = agent
        self._tenant_id = tenant_id
        self._metadata = metadata or {}

    async def run_bot(self, handle_sigint: bool = True):
        logger.info("Starting bot")
        provider_session_id = self._metadata.get("pc_id")
        session_id = self._metadata.get("session_id")
        if not session_id:
            logger.error("No session_id found in metadata for WebRTC service")
            return

        db = get_database(self._tenant_id, MongoClient.get_client())
        session_manager = SessionManager(db)

        # Create Smart Turn analyzer and VAD analyzer from agent configuration
        turn_analyzer = create_turn_analyzer(self._agent.config.smart_turn)
        vad_analyzer = create_vad_analyzer(self._agent.config.vad, enable_turn_detection=bool(turn_analyzer))

        # Create Krisp VIVA noise suppression filter from agent configuration
        krisp_filter = create_krisp_viva_filter(self._agent.config.krisp_viva_filter)

        # Log which filter is being used
        if krisp_filter:
            filter_type = type(krisp_filter).__name__
            logger.info(f"🎤 Using audio filter: {filter_type} for WebRTC transport")
        else:
            logger.info("🎤 No audio filter configured for WebRTC transport")

        transport = SmallWebRTCTransport(
            webrtc_connection=self._webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_in_filter=krisp_filter,
                vad_analyzer=vad_analyzer,
                turn_analyzer=turn_analyzer,
            ),
        )

        session = await session_manager.get_session(self._metadata["session_id"])

        # Build and set session context
        user_details_dict = session.created_by.model_dump() if session.created_by else None
        await self._agent.set_session_context(
            session_id=session.session_id,
            transport_name="webrtc",
            db=db,
            tenant_id=self._tenant_id,
            provider_session_id=self._webrtc_connection.pc_id,
            transport_metadata=self._metadata,
            user_details=user_details_dict,
            call_data=None
        )

        pipeline_params = PipelineParams(
            allow_voip=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=self._agent.config.report_only_initial_ttfb,
        )

        await run_pipeline(transport=transport, agent=self._agent, session_id=session_id, tenant_id=self._tenant_id, provider_session_id=provider_session_id, transport_name="webrtc", pipeline_params=pipeline_params, metadata=self._metadata, handle_sigint=handle_sigint)
