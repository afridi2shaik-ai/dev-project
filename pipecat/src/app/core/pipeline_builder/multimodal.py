from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.transports.base_transport import BaseTransport

from app.schemas.services.agent import AgentConfig


def build_multimodal_pipeline(
    transport: BaseTransport,
    llm_service,
    context_aggregator,
    agent_config: AgentConfig,
    transcript_processor: TranscriptProcessor,
) -> tuple[Pipeline, AudioBufferProcessor]:
    """Create a multimodal speech-to-speech pipeline chain.

    Chain:
        input → rtvi → transcript.user → context.user → llm → transcript.assistant → output → audiobuffer → context.assistant
    """
    audiobuffer = AudioBufferProcessor()
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            transcript_processor.user(),
            context_aggregator.user(),
            llm_service,
            transcript_processor.assistant(),
            transport.output(),
            audiobuffer,
            context_aggregator.assistant(),
        ]
    )

    return pipeline, audiobuffer
