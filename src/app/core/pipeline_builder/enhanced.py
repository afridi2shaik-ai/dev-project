"""Enhanced pipeline builder with configurable processor providers."""

from typing import Any

from loguru import logger
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.filters.stt_mute_filter import STTMuteConfig, STTMuteFilter, STTMuteStrategy
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.transports.base_transport import BaseTransport

from app.processors.transcription_filter import TranscriptionFilter
from app.processors.webrtc_text_sender import WebRTCTextSender
from app.processors.webrtc_user_text_sender import WebRTCUserTextSender
from app.schemas.services.agent import AgentConfig, SpeakFirstMessageConfig


def build_enhanced_pipeline(
    transport: BaseTransport,
    stt_service,
    llm_service,
    tts_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
    hangup_observer=None,
    voicemail_detector=None,
    transport_name: str = "",
) -> tuple[Pipeline, AudioBufferProcessor, Any, TranscriptionFilter | None]:
    """Create an enhanced pipeline with configurable processors.

    Supports automatic transcription filtering to prevent empty STT responses.
    Also blocks transcriptions during warm transfer.

    Args:
        transport: Transport for input/output
        stt_service: Speech-to-text service (None for multimodal)
        llm_service: Language model service
        tts_service: Text-to-speech service (None for multimodal)
        context_aggregator: Context management
        agent_config: Full agent configuration including processor settings
        transcript_processor: Transcript handling

    Returns:
        Tuple of (Pipeline, AudioBufferProcessor, UserIdleProcessor or None, TranscriptionFilter or None)
    """
    audiobuffer = AudioBufferProcessor()
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    transcription_filter = None

    logger.info(f"Building enhanced pipeline for {agent_config.pipeline_mode} mode")

    # Common pipeline start
    processors = [
        transport.input(),
        rtvi,
    ]

    # Add STT for traditional mode
    if agent_config.pipeline_mode.value == "traditional" and stt_service:
        processors.append(stt_service)

        # Mute STT until the first bot speech completes in speak-first flows;
        # always mute during function calls to prevent interruptions.
        strategies = {STTMuteStrategy.FUNCTION_CALL}
        if isinstance(agent_config.first_message, SpeakFirstMessageConfig):
            strategies.add(STTMuteStrategy.MUTE_UNTIL_FIRST_BOT_COMPLETE)

        stt_mute_filter = STTMuteFilter(config=STTMuteConfig(strategies=strategies))
        processors.append(stt_mute_filter)

        # Create TranscriptionFilter for empty transcription filtering AND warm transfer blocking
        transcription_filter = TranscriptionFilter()
        processors.append(transcription_filter)

        # Insert voicemail detector after STT filters
        if voicemail_detector:
            processors.append(voicemail_detector.detector())
            logger.info("Added VoicemailDetector.detector() to pipeline (configured for streaming STT with 2.0s aggregation)")

    # User side: transcript.user() then optionally send to WebRTC data channel for live transcript
    processors.append(transcript_processor.user())
    if transport_name == "webrtc":
        processors.append(WebRTCUserTextSender())
        logger.debug("Added WebRTCUserTextSender for live user transcript")
    processors.append(context_aggregator.user())

    # Add filler words processor if enabled (legacy compatibility)
    if agent_config.filler_words.enabled:
        from app.processors.filler_words_processor import FillerWordsProcessor

        filler_processor = FillerWordsProcessor(config=agent_config.filler_words)
        processors.append(filler_processor)
        logger.debug("Added basic filler words processor")

    # Add LLM service
    processors.append(llm_service)

    # For WebRTC: send LLM response text to client before TTS (same as voice-to-chat) so transcript appears before agent speaks
    if transport_name == "webrtc" and agent_config.pipeline_mode.value == "traditional" and tts_service:
        processors.append(WebRTCTextSender())
        logger.debug("Added WebRTCTextSender for assistant text before TTS")

    # Add TTS for traditional mode
    if agent_config.pipeline_mode.value == "traditional" and tts_service:
        processors.append(tts_service)

        # Insert voicemail gate after TTS
        if voicemail_detector:
            processors.append(voicemail_detector.gate())
            logger.info("Added VoicemailDetector.gate() to pipeline")

    # Add idle timeout processor if enabled (legacy compatibility)
    user_idle = None
    if agent_config.idle_timeout.enabled:
        from functools import partial

        from pipecat.processors.user_idle_processor import UserIdleProcessor

        from app.processors.idle_handler import handle_user_idle

        # Pass llm_service to the idle handler callback
        # hangup_observer will be set as processor attribute after creation
        user_idle = UserIdleProcessor(
            callback=partial(handle_user_idle, config=agent_config.idle_timeout, llm_service=llm_service),
            timeout=agent_config.idle_timeout.timeout_seconds,
        )
        # Store references for later access
        user_idle._llm_service = llm_service
        if hangup_observer:
            user_idle._hangup_observer = hangup_observer
        processors.append(user_idle)
        logger.debug("Added basic idle timeout processor")

    # Common pipeline end
    processors.extend(
        [
            transcript_processor.assistant(),
            transport.output(),
            audiobuffer,
            context_aggregator.assistant(),
        ]
    )

    pipeline = Pipeline(processors)
    logger.info(f"Enhanced pipeline created with {len(processors)} processors")

    return pipeline, audiobuffer, user_idle, transcription_filter


def build_enhanced_traditional_pipeline(
    transport: BaseTransport,
    stt_service,
    llm_service,
    tts_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
    hangup_observer=None,
    voicemail_detector=None,
    transport_name: str = "",
) -> tuple[Pipeline, AudioBufferProcessor, Any, TranscriptionFilter | None]:
    """Enhanced traditional pipeline with configurable processors.

    Chain:
        input → rtvi → stt → transcription_filter → voicemail_detector.detector() → transcript.user → [WebRTCUserTextSender] → context.user → [filler_words] → llm → [WebRTCTextSender] → tts → voicemail_detector.gate() → [idle_timeout] → transcript.assistant → output → audiobuffer → context.assistant

    When transport_name is webrtc: WebRTCUserTextSender after user() for live user transcript; WebRTCTextSender after llm (before tts) so assistant text appears before agent speaks.

    VoicemailDetector is configured with 2.0s aggregation timeout to handle streaming STT data properly,
    ensuring tokens like "this"+"is"+"ajay" are aggregated into complete utterances before classification.

    Returns:
        Tuple of (Pipeline, AudioBufferProcessor, UserIdleProcessor or None, TranscriptionFilter or None)
    """
    return build_enhanced_pipeline(
        transport=transport,
        stt_service=stt_service,
        llm_service=llm_service,
        tts_service=tts_service,
        context_aggregator=context_aggregator,
        agent_config=agent_config,
        transcript_processor=transcript_processor,
        hangup_observer=hangup_observer,
        voicemail_detector=voicemail_detector,
        transport_name=transport_name,
    )


def build_enhanced_multimodal_pipeline(
    transport: BaseTransport,
    llm_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
    hangup_observer=None,
) -> tuple[Pipeline, AudioBufferProcessor, Any, TranscriptionFilter | None]:
    """Enhanced multimodal pipeline with configurable processors.

    Chain:
        input → rtvi → transcript.user → context.user → [filler_words] → llm → [idle_timeout] → transcript.assistant → output → audiobuffer → context.assistant
    
    Returns:
        Tuple of (Pipeline, AudioBufferProcessor, UserIdleProcessor or None, TranscriptionFilter or None)
    """
    return build_enhanced_pipeline(
        transport=transport,
        stt_service=None,
        llm_service=llm_service,
        tts_service=None,
        context_aggregator=context_aggregator,
        agent_config=agent_config,
        transcript_processor=transcript_processor,
        hangup_observer=hangup_observer,
    )
