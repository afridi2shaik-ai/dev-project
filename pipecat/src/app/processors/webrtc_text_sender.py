"""Sends full LLM response text to the WebRTC client via the data channel (OutputTransportMessageFrame).

Used in the audio_chat pipeline so the browser chat UI can display bot replies.
Also pushes assistant messages into the transcript accumulator so they appear in logs
(since audio_chat has no TTS, Pipecat's AssistantTranscriptProcessor never emits on_transcript_update).
"""

import datetime
from typing import TYPE_CHECKING

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    OutputTransportMessageFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptionMessage

if TYPE_CHECKING:
    from app.utils.transcript_utils import TranscriptAccumulator


class WebRTCTextSender(FrameProcessor):
    """Buffers LLM text and sends the full response to the client as an app message (data channel).
    Optionally adds assistant messages to transcript_accumulator for logs (audio_chat has no TTS).
    """

    def __init__(self, transcript_accumulator: "TranscriptAccumulator | None" = None):
        super().__init__()
        self._buffer: list[str] = []
        self._transcript_accumulator = transcript_accumulator

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._buffer = []
        elif isinstance(frame, LLMTextFrame):
            text = getattr(frame, "text", "") or ""
            if text:
                self._buffer.append(text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer:
                full_text = "".join(self._buffer).strip()
                if full_text:
                    try:
                        # Send as {text: "..."} so client can parse; Pipecat does json.dumps(message)
                        await self.push_frame(
                            OutputTransportMessageFrame(message={"text": full_text}),
                            direction,
                        )
                    except Exception as e:
                        logger.warning(f"[WebRTCTextSender] Failed to send text to client: {e}")
                    # Push assistant message into transcript for logs (audio_chat has no TTS → no on_transcript_update from Pipecat)
                    if self._transcript_accumulator:
                        try:
                            self._transcript_accumulator.add_message(
                                TranscriptionMessage(
                                    role="assistant",
                                    content=full_text,
                                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                )
                            )
                        except Exception as e:
                            logger.warning(f"[WebRTCTextSender] Failed to add assistant message to transcript: {e}")
            self._buffer = []

        await self.push_frame(frame, direction)
