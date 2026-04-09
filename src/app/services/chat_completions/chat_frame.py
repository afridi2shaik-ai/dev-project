import datetime
from fastapi import WebSocket
from pipecat.frames.frames import (
    Frame,
    LLMTextFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.transcript_processor import TranscriptionMessage
from app.utils.transcript_utils import TranscriptAccumulator


class WebSocketTextOutbound(FrameProcessor):
    """
    Dedicated processor for text-only chat:
    - Buffers streaming LLMTextFrame tokens
    - Sends the complete response as one WebSocket message
    - Stores the final assistant message in the TranscriptAccumulator
    """

    def __init__(self, websocket: WebSocket, accumulator: TranscriptAccumulator, **kwargs):
        super().__init__(**kwargs)
        self.websocket = websocket
        self.accumulator = accumulator
        self._buffer = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._buffer = ""  # Reset for new response

        elif isinstance(frame, LLMTextFrame):
            self._buffer += frame.text  # Accumulate tokens

        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer.strip():
                full_text = self._buffer.strip()

                # Send complete response to client
                try:
                    await self.websocket.send_text(full_text)
                except Exception as e:
                    # Client likely disconnected mid-response
                    pass

                # Store final assistant message in transcript
                assistant_msg = TranscriptionMessage(
                    role="assistant",
                    content=full_text,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                self.accumulator.add_message(assistant_msg)

            self._buffer = ""  # Ready for next turn

        # Always forward the frame downstream (e.g., to context.assistant())
        await self.push_frame(frame, direction)