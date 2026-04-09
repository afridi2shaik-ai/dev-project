"""Audio-chat pipeline: STT → LLM only (no TTS). Used when mode is audio_chat and enable_tts_audio is False."""

from typing import Any

from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.filters.stt_mute_filter import STTMuteConfig, STTMuteFilter, STTMuteStrategy
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.transports.base_transport import BaseTransport

from app.processors.transcription_filter import TranscriptionFilter
from app.processors.webrtc_text_sender import WebRTCTextSender
from app.processors.webrtc_user_text_sender import WebRTCUserTextSender
from app.schemas.services.agent import AgentConfig


def build_audio_chat_pipeline(
    transport: BaseTransport,
    stt_service,
    llm_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
    hangup_observer=None,
    transcript_accumulator=None,
) -> tuple[Pipeline, AudioBufferProcessor, Any, TranscriptionFilter | None]:
    """Build pipeline for audio-chat (voice in, text out): STT → LLM only, no TTS.

    Chain:
        input → rtvi → stt → stt_mute_filter → transcription_filter
        → transcript.user → context.user → [filler_words] → llm
        → transcript.assistant → text_sender → output → audiobuffer → context.assistant
    (No UserIdleProcessor in audio_chat mode.)

    No TTS processor: bot response is delivered as text via transport (client uses onBotOutput etc.).
    Returns same shape as build_enhanced_traditional_pipeline for drop-in use in run_pipeline.
    """
    audiobuffer = AudioBufferProcessor()
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    transcription_filter = None
    user_idle = None

    processors = [
        transport.input(),
        rtvi,
    ]

    if stt_service:
        processors.append(stt_service)
        # Don't use MUTE_UNTIL_FIRST_BOT_COMPLETE in audio_chat: there is no TTS, so that signal
        # never comes and STT would stay muted. First message is sent as text only; user can speak right away.
        strategies = {STTMuteStrategy.FUNCTION_CALL}
        stt_mute_filter = STTMuteFilter(config=STTMuteConfig(strategies=strategies))
        processors.append(stt_mute_filter)
        transcription_filter = TranscriptionFilter()
        processors.append(transcription_filter)

    processors.extend([
        transcript_processor.user(),
        WebRTCUserTextSender(),
        context_aggregator.user(),
    ])

    if agent_config.filler_words.enabled:
        from app.processors.filler_words_processor import FillerWordsProcessor
        filler_processor = FillerWordsProcessor(config=agent_config.filler_words)
        processors.append(filler_processor)
    processors.append(llm_service)
    processors.extend([
        transcript_processor.assistant(),
        WebRTCTextSender(transcript_accumulator=transcript_accumulator),
        transport.output(),
        audiobuffer,
        context_aggregator.assistant(),
    ])

    pipeline = Pipeline(processors)

    return pipeline, audiobuffer, user_idle, transcription_filter
