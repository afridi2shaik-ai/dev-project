import datetime
import json
from typing import Any

from pipecat.processors.transcript_processor import TranscriptionMessage


class TranscriptAccumulator:
    """Accumulates a structured transcript of the conversation.

    This class no longer processes raw frames directly. Instead, it receives
    structured `TranscriptionMessage` objects from the Pipecat `TranscriptProcessor`
    and app-specific events (tool calls, errors) from a dedicated `AppObserver`.
    This ensures a clean separation of concerns and robust transcript creation.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._tool_calls: dict[str, str] = {}  # Maps call_id to tool_name
        self._processed_tool_calls: set[str] = set()  # Track processed tool call call_ids
        self._processed_tool_results: set[str] = set()  # Track processed tool result call_ids

    def add_message(self, message: TranscriptionMessage) -> None:
        """Adds a structured user or assistant message to the transcript."""
        new_message = {"role": message.role, "text": message.content, "timestamp": message.timestamp or datetime.datetime.now(datetime.UTC).isoformat()}

        # Check for duplicates - avoid adding the same message content within a small time window
        content = new_message["text"]
        role = new_message["role"]
        normalized_content = _normalize_text(content)

        # Look for exact and near-duplicates in the last few messages
        for recent_msg in self.messages[-5:]:  # Check last 5 messages
            if recent_msg.get("role") == role and recent_msg.get("type", None) is None:  # Only check regular messages, not tool calls
                recent_content = recent_msg.get("text", "")
                recent_normalized = _normalize_text(recent_content)

                # Check for exact match or normalized match (handles extra spaces, etc.)
                if recent_content == content or recent_normalized == normalized_content:
                    # This is likely a duplicate - skip adding
                    return

        self.messages.append(new_message)
        # Sort by timestamp to ensure chronological order, as events might arrive out of order.
        self.messages.sort(key=lambda x: x.get("timestamp") or "")

    def add_tool_call(self, tool_name: str, tool_args: dict[str, Any], call_id: str) -> None:
        """Adds a tool call event to the transcript."""
        # Check if we've already processed this tool call
        if call_id in self._processed_tool_calls:
            return  # Avoid duplicates

        # Store the tool call mapping for tool result processing
        self._tool_calls[call_id] = tool_name

        # Mark this tool call as processed
        self._processed_tool_calls.add(call_id)

        self.messages.append(
            {
                "role": "assistant",
                "type": "tool_call",
                "text": f"[Calling tool '{tool_name}' with arguments: {json.dumps(tool_args, ensure_ascii=False)}]",
                "tool_details": {
                    "name": tool_name,
                    "arguments": tool_args,
                    "id": call_id,
                },
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )
        self.messages.sort(key=lambda x: x.get("timestamp") or "")

    def add_tool_result(self, call_id: str | None, result: dict[str, Any]) -> None:
        """Adds a tool result event to the transcript."""
        # Silently ignore results without a call_id. These are typically
        # intermediate frames from the LLM service that will be followed by an
        # enriched frame from the context aggregator that includes the call_id.
        # This prevents warnings and duplicate transcript entries.
        if not call_id:
            return

        # Check if we've already processed this tool result
        if call_id in self._processed_tool_results:
            return

        tool_name = self._tool_calls.get(call_id)
        if not tool_name:
            # This is not necessarily a warning. The same frame can be pushed
            # multiple times through the pipeline, so we just ignore duplicates.
            return

        self.messages.append(
            {
                "role": "assistant",
                "type": "tool_result",
                "text": f"[Tool '{tool_name}' returned: {json.dumps(result, ensure_ascii=False)}]",
                "tool_details": {
                    "name": tool_name,
                    "result": result,
                    "id": call_id,
                },
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )

        # Mark this tool result as processed to prevent duplicates
        self._processed_tool_results.add(call_id)

        # Keep the tool call mapping for potential debugging, but mark result as processed
        # del self._tool_calls[call_id]  # Commented out to avoid losing tool call info

        self.messages.sort(key=lambda x: x.get("timestamp") or "")

    def add_error(self, error: str) -> None:
        """Adds a pipeline error event to the transcript for debugging."""
        self.messages.append({"role": "system", "type": "error", "text": f"[Pipeline Error: {error}]", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()})
        self.messages.sort(key=lambda x: x.get("timestamp") or "")

    def get_tool_usage_summary(self) -> dict[str, int]:
        """Returns a summary of how many times each tool was called."""
        summary: dict[str, int] = {}
        for msg in self.messages:
            if msg.get("type") == "tool_call":
                tool_name = msg.get("tool_details", {}).get("name")
                if tool_name:
                    summary[tool_name] = summary.get(tool_name, 0) + 1
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the transcript."""
        # Clean up any potential empty messages that might have resulted from previous logic
        self.messages = [m for m in self.messages if m.get("text")]
        return {"messages": self.messages}


def _normalize_text(text: str) -> str:
    """Helper to clean up common artifacts from streaming LLM text and TTS processing.

    This function normalizes text to help detect duplicates that might have slight
    variations due to TTS chunking, streaming, or processing artifacts.
    """
    if not isinstance(text, str):
        return ""

    # Remove extra whitespace and normalize spacing
    normalized = " ".join(text.split())

    # Convert to lowercase for comparison (preserves original case in transcript)
    normalized = normalized.lower()

    # Remove common punctuation that might vary
    normalized = normalized.replace(".", "").replace(",", "").replace("!", "").replace("?", "")

    # Remove extra characters that might be added during processing
    normalized = normalized.strip()

    return normalized
