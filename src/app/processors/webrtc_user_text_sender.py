"""Sends transcriptions (user or assistant) to the WebRTC client via the data channel.

Used in the audio_chat pipeline for user transcript, and in the traditional WebRTC pipeline
for both user and assistant live transcript. Listens for TranscriptionUpdateFrame and pushes
OutputTransportMessageFrame(message={"role": "user"|"assistant", "text": content}) so the
browser can display live transcript for either role.
"""

from loguru import logger
from pipecat.frames.frames import Frame, OutputTransportMessageFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptionUpdateFrame


class WebRTCUserTextSender(FrameProcessor):
    """When transcript is updated (TranscriptionUpdateFrame), sends it to the client as app message (user or assistant)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, TranscriptionUpdateFrame):
            messages = getattr(frame, "messages", [])
            for message in messages:
                role = getattr(message, "role", None)
                if role in ("user", "assistant"):
                    text = getattr(message, "content", "") or getattr(message, "text", "")
                    if text and str(text).strip():
                        try:
                            await self.push_frame(
                                OutputTransportMessageFrame(
                                    message={"role": role, "text": str(text).strip()}
                                ),
                                direction,
                            )
                        except Exception as e:
                            logger.warning(
                                f"[WebRTCUserTextSender] Failed to send {role} text to client: {e}"
                            )

        await self.push_frame(frame, direction)
