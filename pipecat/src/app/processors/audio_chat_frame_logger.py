"""Pass-through processor for audio_chat pipeline (kept for optional re-enable of frame logging)."""

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class AudioChatFrameLogger(FrameProcessor):
    """Pass-through processor; frame logging can be re-enabled here for debugging."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
