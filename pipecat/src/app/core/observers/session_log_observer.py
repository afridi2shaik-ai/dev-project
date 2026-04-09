import time

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    CancelFrame,
    EndFrame,
    FunctionCallResultFrame,
    FunctionCallsStartedFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.utils.session_log_utils import SessionLogAccumulator


class SessionLogObserver(BaseObserver):
    """
    An observer that captures key pipeline events and logs them to a plain-text
    file at the end of the session.
    """

    def __init__(self, transport_name: str, session_id: str):
        super().__init__()
        self._transport_name = transport_name
        self._session_id = session_id
        self.accumulator = SessionLogAccumulator()
        self._assistant_response_buffer = []
        # For per-turn latency metrics
        self._last_user_stop_time: float | None = None
        self._last_assistant_text: str | None = None
        self._last_user_text: str | None = None
        self._latencies: list[float] = []
        self._latency_summary_logged = False
        self._session_end_logged = False
        # For deduplication
        self._last_log_message = None
        self._last_log_time = 0

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        log_messages = []

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._last_user_stop_time = time.time()
        elif isinstance(frame, TranscriptionFrame):
            user_text = frame.text.strip()
            if user_text and user_text != self._last_user_text:
                log_messages.append(f'USER: "{user_text}"')
                self._last_user_text = user_text
        elif isinstance(frame, BotStartedSpeakingFrame):
            if self._last_user_stop_time:
                latency_s = time.time() - self._last_user_stop_time
                self._latencies.append(latency_s)
                log_messages.append(f"LATENCY: {latency_s:.2f}s")
                self._last_user_stop_time = None
        elif isinstance(frame, LLMTextFrame):
            self._assistant_response_buffer.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            full_response = "".join(self._assistant_response_buffer).strip()
            if full_response and full_response != self._last_assistant_text:
                log_messages.append(f'ASSISTANT: "{full_response}"')
                self._last_assistant_text = full_response
            self._assistant_response_buffer = []
        elif isinstance(frame, FunctionCallsStartedFrame):
            function_calls = getattr(frame, "function_calls", [])
            for call in function_calls:
                try:
                    tool_name = call.function_name
                    call_id = call.tool_call_id
                    if tool_name:
                        suffix = f" (call_id: {call_id})" if call_id else ""
                        log_messages.append(f"TOOL_CALL: {tool_name}{suffix}")
                except AttributeError:
                    log_messages.append("TOOL_CALL: [unparseable]")
        elif isinstance(frame, FunctionCallResultFrame):
            call_id = getattr(frame, "tool_call_id", None)
            result = getattr(frame, "result", {})
            status = "success"
            if isinstance(result, dict):
                if result.get("error") or result.get("success") is False:
                    status = "failed"
            log_messages.append(f"TOOL_RESULT: {call_id or 'unknown'} ({status})")
        elif isinstance(frame, TTSSpeakFrame):
            assistant_text = frame.text.strip()
            if assistant_text and assistant_text != self._last_assistant_text:
                log_messages.append(f'ASSISTANT: "{assistant_text}"')
                self._last_assistant_text = assistant_text
        elif isinstance(frame, EndFrame):
            if not self._session_end_logged:
                log_messages.append("SESSION: ended")
                self._append_latency_summary(log_messages)
                self._session_end_logged = True
        elif isinstance(frame, CancelFrame):
            if not self._session_end_logged:
                log_messages.append("SESSION: cancelled")
                self._append_latency_summary(log_messages)
                self._session_end_logged = True

        if log_messages:
            for msg in log_messages:
                # Handle deduplication
                now = time.time()
                if msg == self._last_log_message and (now - self._last_log_time) < 0.1:
                    continue

                self.accumulator.add_log_entry(msg)
                self._last_log_message = msg
                self._last_log_time = now

    def _append_latency_summary(self, log_messages: list[str]) -> None:
        if self._latency_summary_logged or not self._latencies:
            return
        avg_latency = sum(self._latencies) / len(self._latencies)
        min_latency = min(self._latencies)
        max_latency = max(self._latencies)
        log_messages.append(
            "LATENCY SUMMARY: Avg {:.2f}s, Min {:.2f}s, Max {:.2f}s".format(
                avg_latency, min_latency, max_latency
            )
        )
        self._latency_summary_logged = True
