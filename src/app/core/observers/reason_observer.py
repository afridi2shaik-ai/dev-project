from loguru import logger
from pipecat.frames.frames import CancelFrame, EndFrame, FunctionCallResultFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.utils.hangup_utils import save_hangup_reason
from app.utils.transcript_utils import TranscriptAccumulator


class HangupObserver(BaseObserver):
    """
    An observer that determines the reason for call disconnection and saves it
    to a dedicated file. It acts as the single source of truth for why a
    session ended.
    """

    def __init__(self, transport_name: str, session_id: str, transcript_accumulator: TranscriptAccumulator):
        super().__init__()
        self._transport_name = transport_name
        self._session_id = session_id
        self._transcript = transcript_accumulator
        self.reason = "pipeline_completed"  # Default reason
        self.details = {}
        self._saved = False

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if isinstance(frame, FunctionCallResultFrame):
            call_id = getattr(frame, "call_id", None)
            if call_id:
                tool_name = self._transcript._tool_calls.get(call_id, "unknown_tool")
                if tool_name == "hangup_call":
                    self.reason = "assistant_hangup"
                    self.details = getattr(frame, "result", {})
                    # We can save immediately here because we know this is the final reason
                    await self._save()

        # The final save on End/Cancel acts as a fallback for normal completion
        if not self._saved and isinstance(frame, (EndFrame, CancelFrame)):
            await self._save()

    async def set_reason_client_disconnected(self):
        """
        Allows external components like transport event handlers to set the
        disconnection reason explicitly.
        """
        logger.debug("Setting disconnection reason to client_disconnected")
        self.reason = "client_disconnected"
        self.details = {"message": "Client connection was lost abruptly."}
        await self._save()

    async def _save(self):
        # Ensure we only save the reason once to avoid race conditions
        if self._saved:
            return
        self._saved = True
        logger.info(f"Saving disconnection reason '{self.reason}' for session {self._session_id}")
        data = {"disconnection_reason": self.reason, "details": self.details}
        await save_hangup_reason(self._transport_name, self._session_id, data)
