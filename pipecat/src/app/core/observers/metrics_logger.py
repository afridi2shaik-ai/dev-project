from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    MetricsFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline

from app.utils.metrics_utils import (
    MetricsAccumulator,
    accumulate_metrics_from_frame,
)

# Optional: import concrete services to enrich metrics logging output
try:
    from pipecat.services.openai.llm import OpenAILLMService  # type: ignore
except Exception:  # pragma: no cover - optional
    OpenAILLMService = None  # type: ignore
try:
    from pipecat.services.openai.stt import OpenAISTTService  # type: ignore
except Exception:  # pragma: no cover - optional
    OpenAISTTService = None  # type: ignore
try:
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService  # type: ignore
except Exception:  # pragma: no cover - optional
    ElevenLabsTTSService = None  # type: ignore
try:
    from pipecat.services.sarvam.tts import SarvamTTSService  # type: ignore
except Exception:  # pragma: no cover - optional
    SarvamTTSService = None  # type: ignore


class MetricsLogger(BaseObserver):
    """
    Observer that accumulates metrics and transcripts during a session and
    persists them at End/Cancel. Designed for reuse across transports.
    """

    def __init__(self, pipeline: Pipeline, transport_name: str, session_id: str):
        super().__init__()
        self._pipeline = pipeline
        self._transport_name = transport_name
        self._session_id = session_id
        self._logged = False
        self._accumulator = MetricsAccumulator()

    async def on_push_frame(self, data: FramePushed):
        # Accumulate metrics from MetricsFrames
        if isinstance(data.frame, MetricsFrame):
            accumulate_metrics_from_frame(self._accumulator, data.frame)

        # On session end, log metrics once
        if not self._logged and isinstance(data.frame, (EndFrame, CancelFrame)):
            await self._log_metrics()
            self._logged = True

    async def _log_metrics(self):
        logger.info(f"--- End-of-Call Metrics for {self._transport_name} session {self._session_id} ---")
        # Log accumulated metrics from the accumulator
        metrics_dict = self._accumulator.to_dict()

        # Log Timing Metrics
        if metrics_dict.get("ttfb_metrics"):
            first_response = metrics_dict["ttfb_metrics"].get("first_response_seconds")
            if first_response is not None:
                logger.info(f"  - Overall TTFB: {first_response:.4f}s")

            by_category = metrics_dict["ttfb_metrics"].get("by_category_first_seconds", {})
            for category, value in by_category.items():
                if value is not None:
                    logger.info(f"    - First TTFB ({category.upper()}): {value:.4f}s")

        if metrics_dict.get("timing_totals"):
            for category, value in metrics_dict["timing_totals"].items():
                if value > 0:
                    logger.info(f"  - Total Processing Time ({category.upper()}): {value:.4f}s")

        # Log Usage Metrics
        if metrics_dict.get("token_usage"):
            prompt_tokens = metrics_dict["token_usage"].get("prompt_tokens", 0)
            completion_tokens = metrics_dict["token_usage"].get("completion_tokens", 0)
            if prompt_tokens > 0 or completion_tokens > 0:
                logger.info("  - LLM Usage:")
                logger.info(f"    - Prompt Tokens: {prompt_tokens}")
                logger.info(f"    - Completion Tokens: {completion_tokens}")

        if metrics_dict.get("tts_usage"):
            characters = metrics_dict["tts_usage"].get("characters", 0)
            if characters > 0:
                logger.info(f"  - TTS Usage: {characters} characters")

        logger.info("--- End of Metrics ---")

    def get_metrics_accumulator(self) -> MetricsAccumulator:
        return self._accumulator
