from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.utils.transcript_utils import TranscriptAccumulator


class SummarizationObserver(BaseObserver):
    """
    An observer that provides the accumulated transcript for summarization at the
    end of the call. It shares the TranscriptAccumulator from another observer.
    """

    def __init__(self, transport_name: str, session_id: str, transcript_accumulator: TranscriptAccumulator):
        super().__init__()
        self._transcript = transcript_accumulator
        # Keep these for context, though they are not used in this simplified version
        self._transport_name = transport_name
        self._session_id = session_id

    @property
    def messages(self):
        return self._transcript.to_dict().get("messages", [])

    # This observer no longer needs to process frames directly.
    # It will get the completed transcript from the shared accumulator.
    async def on_push_frame(self, data: FramePushed):
        pass
