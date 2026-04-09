from functools import partial

from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.transports.base_transport import BaseTransport

from app.core.pipeline_builder.mute_utils import add_first_speech_mute_if_needed
from app.processors.filler_words_processor import FillerWordsProcessor
from app.processors.idle_handler import handle_user_idle
from app.processors.transcription_filter import TranscriptionFilter
from app.schemas.services.agent import AgentConfig


def build_traditional_pipeline(
    transport: BaseTransport,
    stt_service,
    llm_service,
    tts_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
) -> tuple[Pipeline, AudioBufferProcessor]:
    """Create the standard pipeline chain and return pipeline plus audio buffer.

    Chain:
        input → rtvi → stt → transcription_filter → transcript.user → context.user → filler_words → llm → tts → user_idle → transcript.assistant → output → audiobuffer → context.assistant
    """
    audiobuffer = AudioBufferProcessor()
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    processors = [
        transport.input(),
        rtvi,
        stt_service,
    ]
    
    # Mute STT during the bot's first speech in speak-first flows
    add_first_speech_mute_if_needed(processors, agent_config, stt_enabled=bool(stt_service))
    
    processors.append(TranscriptionFilter())  # Filter empty transcriptions before they reach the LLM
    processors.extend([
        transcript_processor.user(),
        context_aggregator.user(),
    ])

    if agent_config.filler_words.enabled:
        filler_words = FillerWordsProcessor(config=agent_config.filler_words)
        processors.append(filler_words)

    processors.append(llm_service)
    processors.append(tts_service)  # TTS service (could be MultiTTSRouter)

    # Add idle processor AFTER TTS so it can see bot speaking events
    if agent_config.idle_timeout.enabled:
        user_idle = UserIdleProcessor(
            callback=partial(handle_user_idle, config=agent_config.idle_timeout),
            timeout=agent_config.idle_timeout.timeout_seconds,
        )
        processors.append(user_idle)

    processors.extend(
        [
            transcript_processor.assistant(),
            transport.output(),
            audiobuffer,
            context_aggregator.assistant(),
        ]
    )

    pipeline = Pipeline(processors)
    return pipeline, audiobuffer


