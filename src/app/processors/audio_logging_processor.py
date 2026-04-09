"""Audio Logging Processor

This processor logs StartFrame and audio frame processing to help debug audio capture issues.
"""

from loguru import logger
from pipecat.frames.frames import Frame, StartFrame, InputAudioRawFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class AudioLoggingProcessor(FrameProcessor):
    """Logs StartFrame and audio frames for debugging audio capture issues."""

    def __init__(self, session_id: str):
        super().__init__()
        self._session_id = session_id
        self._start_frame_received = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and log important audio-related frames."""
        await super().process_frame(frame, direction)

        # Log StartFrame to track sample rate initialization
        if isinstance(frame, StartFrame):
            self._start_frame_received = True
            sample_rate = getattr(frame, 'audio_out_sample_rate', None) or getattr(frame, 'audio_in_sample_rate', None)
            logger.info(f"🎬 StartFrame received for session {self._session_id}: sample_rate={sample_rate}, audio_in_enabled={getattr(frame, 'audio_in_enabled', None)}, audio_out_enabled={getattr(frame, 'audio_out_enabled', None)}")

        # Log audio frames to track audio flow
        if isinstance(frame, InputAudioRawFrame):
            logger.debug(f"🎤 InputAudioRawFrame: session={self._session_id}, sample_rate={frame.sample_rate}, audio_size={len(frame.audio)}")
        elif isinstance(frame, OutputAudioRawFrame):
            logger.debug(f"🔊 OutputAudioRawFrame: session={self._session_id}, sample_rate={frame.sample_rate}, audio_size={len(frame.audio)}")

        # Pass all frames through
        await self.push_frame(frame, direction)

