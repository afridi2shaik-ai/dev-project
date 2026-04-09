import datetime

from loguru import logger
from pipecat.frames.frames import CancelFrame, EndFrame, FunctionCallResultFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.schemas.log_schema import Artifact, ArtifactType
from app.utils.transcript_utils import TranscriptAccumulator


class HangupObserver(BaseObserver):
    """
    An observer that determines the reason for call disconnection and prepares
    it as an artifact for logging.
    
    Also tracks the exact time when hangup occurred, which is critical for
    accurate call duration calculation.
    """

    def __init__(self, session_id: str, transcript_accumulator: TranscriptAccumulator):
        super().__init__()
        self._session_id = session_id
        self._transcript = transcript_accumulator
        self.reason = "pipeline_completed"  # Default reason
        self.details = {}
        self._saved = False
        self._hangup_artifact: Artifact | None = None
        self.hangup_time: datetime.datetime | None = None  # Track when hangup was initiated

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if isinstance(frame, FunctionCallResultFrame):
            # Instead of looking up the tool by call_id (which can cause a race condition
            # with the AppObserver), we inspect the result payload directly.
            result = getattr(frame, "result", {})
            if isinstance(result, dict) and result.get("action") == "hangup":
                # CRITICAL: Capture the EXACT time when hangup was initiated
                # Only capture once - the FIRST time we see the hangup action
                if self.hangup_time is None:
                    self.hangup_time = datetime.datetime.now(datetime.UTC)
                    logger.info(f"Hangup initiated for session {self._session_id} at {self.hangup_time.isoformat()}")

                self.reason = "assistant_hangup"
                self.details = result
                # We can save immediately here because we know this is the final reason
                await self._save()

        # The final save on End/Cancel acts as a fallback for normal completion
        if not self._saved and isinstance(frame, (EndFrame, CancelFrame)):
            await self._save()

    async def set_reason_client_disconnected(self):
        """
        Allows external components like transport event handlers to set the
        disconnection reason explicitly.
        
        IMPORTANT: Only sets hangup_time if not already set (e.g., by hangup_call tool).
        This preserves the earliest/most accurate hangup time.
        """
        # CRITICAL: Only capture time if hangup_time hasn't been set yet
        # If hangup_call tool was used, its timestamp takes precedence
        if self.hangup_time is None:
            self.hangup_time = datetime.datetime.now(datetime.UTC)
            logger.info(f"Client disconnected for session {self._session_id} at {self.hangup_time.isoformat()}")
        else:
            logger.info(f"Client disconnected for session {self._session_id}, but hangup_time already set to {self.hangup_time.isoformat()} (preserving earlier timestamp)")

        # Only update reason if not already saved (e.g., assistant_hangup takes precedence)
        if not self._saved:
            logger.debug("Setting disconnection reason to client_disconnected")
            self.reason = "client_disconnected"
            self.details = {"message": "Client connection was lost abruptly."}
            await self._save()
        else:
            logger.debug(f"Hangup reason already saved as '{self.reason}', not updating to client_disconnected")

    async def set_reason_idle_timeout(self):
        """
        Sets the disconnection reason to idle_timeout when user idle timeout is exhausted.
        
        IMPORTANT: Only sets hangup_time if not already set (e.g., by hangup_call tool).
        This preserves the earliest/most accurate hangup time.
        """
        # CRITICAL: Only capture time if hangup_time hasn't been set yet
        # If hangup_call tool was used, its timestamp takes precedence
        if self.hangup_time is None:
            self.hangup_time = datetime.datetime.now(datetime.UTC)
            logger.info(f"Idle timeout triggered for session {self._session_id} at {self.hangup_time.isoformat()}")
        else:
            logger.info(f"Idle timeout triggered for session {self._session_id}, but hangup_time already set to {self.hangup_time.isoformat()} (preserving earlier timestamp)")

        # Only update reason if not already saved (e.g., assistant_hangup takes precedence)
        if not self._saved:
            logger.debug("Setting disconnection reason to idle_timeout")
            self.reason = "idle_timeout"
            self.details = {"message": "User idle timeout exceeded. Call disconnected due to inactivity."}
            await self._save()
        else:
            logger.debug(f"Hangup reason already saved as '{self.reason}', not updating to idle_timeout")

    async def set_reason_voicemail(self):
        """
        Sets the disconnection reason to voicemail when the call reached voicemail
        and the agent left a message.
        """
        if self.hangup_time is None:
            self.hangup_time = datetime.datetime.now(datetime.UTC)
            logger.info(f"Voicemail message delivered for session {self._session_id} at {self.hangup_time.isoformat()}")
        
        if not self._saved:
            logger.debug("Setting disconnection reason to voicemail")
            self.reason = "voicemail"
            self.details = {"message": "Call reached voicemail. Agent left a message and disconnected."}
            await self._save()
        else:
            logger.debug(f"Hangup reason already saved as '{self.reason}', not updating to voicemail")

    async def _save(self):
        # Ensure we only save the reason once to avoid race conditions
        if self._saved:
            return
        self._saved = True
        logger.info(f"Saving disconnection reason '{self.reason}' for session {self._session_id}")
        data = {"disconnection_reason": self.reason, "details": self.details}
        self._hangup_artifact = Artifact(artifact_type=ArtifactType.HANGUP, content=data)

    def get_hangup_artifact(self) -> Artifact | None:
        return self._hangup_artifact
