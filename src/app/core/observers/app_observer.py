import json

from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    ErrorFrame,
    FunctionCallResultFrame,
    FunctionCallsStartedFrame,
    TTSSpeakFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.utils.transcript_utils import TranscriptAccumulator


class AppObserver(BaseObserver):
    """An observer that listens for app-specific events (tool calls, errors)
    and updates the central TranscriptAccumulator. This separates concerns from
    the built-in TranscriptProcessor which handles user/assistant text.
    """

    def __init__(self, transcript_accumulator: TranscriptAccumulator):
        super().__init__()
        self._transcript = transcript_accumulator
        # Optional callback for first message completion detection (voicemail flow)
        self._first_message_callback = None

    def _process_function_call(self, call) -> None:
        """Process a single function call and add it to the transcript."""
        try:
            tool_name = call.function_name
            call_id = call.tool_call_id
            # Arguments can be a string or already a dict
            arguments = call.arguments
            tool_args = json.loads(arguments) if isinstance(arguments, str) else arguments

            if tool_name and call_id and isinstance(tool_args, dict):
                self._transcript.add_tool_call(tool_name, tool_args, call_id)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Could not parse function call object: {call}, error: {e}")

    def _handle_function_calls_frame(self, frame: FunctionCallsStartedFrame) -> None:
        """Handle function calls started frame by processing each function call."""
        function_calls = getattr(frame, "function_calls", [])
        for call in function_calls:
            self._process_function_call(call)

    def _handle_function_result_frame(self, frame: FunctionCallResultFrame) -> None:
        """Handle function call result frame."""
        call_id = getattr(frame, "tool_call_id", None)
        result = getattr(frame, "result", {})
        self._transcript.add_tool_result(call_id, result)

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame

        if isinstance(frame, ErrorFrame):
            self._transcript.add_error(frame.error)
        elif isinstance(frame, FunctionCallsStartedFrame):
            self._handle_function_calls_frame(frame)
        elif isinstance(frame, FunctionCallResultFrame):
            self._handle_function_result_frame(frame)
        elif isinstance(frame, TTSSpeakFrame):
            # Skip capturing TTSSpeakFrame here to avoid duplicates with the transcript processor
            # The transcript processor should handle all TTS frames, including those from tools
            pass
        elif isinstance(frame, BotStoppedSpeakingFrame):
            # Trigger first message callback if set (used for voicemail detection flow)
            if self._first_message_callback is not None:
                callback = self._first_message_callback
                self._first_message_callback = None  # Clear callback to prevent multiple calls
                logger.info(f"Calling first message callback: {callback}")
                try:
                    # Ensure callback is a coroutine function and call it safely
                    if callable(callback):
                        await callback(frame)
                        logger.info("First message callback completed successfully")
                    else:
                        logger.error(f"First message callback is not callable: {callback}")
                except Exception as e:
                    logger.warning(f"Error in first message callback: {e}, callback type: {type(callback)}")
                    import traceback
                    logger.warning(f"Traceback: {traceback.format_exc()}")
            # Intentionally no logging when callback isn't set to avoid log spam.
