from fastapi import WebSocket
from loguru import logger
from pipecat.pipeline.task import PipelineParams
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
)

from app.agents import BaseAgent
from app.core import settings
from app.services.audio import create_krisp_viva_filter
from app.services.turn.turn_service import create_turn_analyzer
from app.services.vad import create_vad_analyzer

from .base_transport_service import run_pipeline
from .custom_websocket_transport import CustomFastAPIWebsocketTransport


async def run_twilio_bot(websocket: WebSocket, stream_sid: str, call_sid: str, session_id: str, tenant_id: str, agent: BaseAgent, start_data: dict):
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.TWILIO_ACCOUNT_SID,
        auth_token=settings.TWILIO_AUTH_TOKEN,
    )

    # Create Smart Turn analyzer and VAD analyzer from agent configuration
    turn_analyzer = create_turn_analyzer(agent.config.smart_turn)
    vad_analyzer = create_vad_analyzer(agent.config.vad, enable_turn_detection=bool(turn_analyzer))

    # Create Krisp VIVA noise suppression filter from agent configuration
    # No sample rate check needed - Krisp VIVA supports 8kHz (unlike Koala)
    krisp_filter = create_krisp_viva_filter(agent.config.krisp_viva_filter)

    # Log which filter is being used
    if krisp_filter:
        filter_type = type(krisp_filter).__name__
        logger.info(f"🎤 Using audio filter: {filter_type} for Twilio transport (8kHz)")
    else:
        logger.info("🎤 No audio filter configured for Twilio transport")

    transport = CustomFastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            audio_in_filter=krisp_filter,
            vad_analyzer=vad_analyzer,
            turn_analyzer=turn_analyzer,
            serializer=serializer,
        ),
    )

    pipeline_params = PipelineParams(
        audio_in_sample_rate=8000,
        audio_out_sample_rate=8000,
        enable_metrics=True,
        enable_usage_metrics=True,
        report_only_initial_ttfb=agent.config.report_only_initial_ttfb,
    )

    await run_pipeline(
        transport=transport,
        agent=agent,
        session_id=session_id,
        tenant_id=tenant_id,
        provider_session_id=call_sid,
        transport_name="twilio",
        pipeline_params=pipeline_params,
        metadata=start_data,
    )
