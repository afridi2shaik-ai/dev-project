import csv
import datetime
import io
import json
from typing import Any

from app.schemas.log_schema import Log


def logs_to_csv(logs: list[Log]) -> bytes:
    """Convert logs into a standard CSV representation."""
    fieldnames = [
        "log_id",
        "session_id",
        "agent_type",
        "log_type",
        "session_state",
        "transport",
        "assistant_id",
        "assistant_name",
        "duration_seconds",
        "created_at",
        "updated_at",
        "participants",
        "content",
    ]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for log in logs:
        writer.writerow(log_to_row(log))
    return buffer.getvalue().encode("utf-8")


def log_to_row(log: Log) -> dict[str, Any]:
    """Flatten a log into a dictionary suitable for CSV writing."""

    def dumps(obj: object) -> str:
        return json.dumps(obj, default=str, ensure_ascii=False)

    return {
        "log_id": log.log_id,
        "session_id": log.session_id,
        "agent_type": log.agent_type,
        "log_type": log.log_type,
        "session_state": log.session_state,
        "transport": log.transport,
        "assistant_id": log.assistant_id,
        "assistant_name": log.assistant_name,
        "duration_seconds": log.duration_seconds,
        "created_at": log.created_at.isoformat() if log.created_at else "",
        "updated_at": log.updated_at.isoformat() if log.updated_at else "",
        "participants": dumps(log.participants),
        "content": dumps(log.content),
    }


def logs_to_flat_csv(logs: list[Log]) -> bytes:
    """Convert logs into a flattened, human-friendly CSV.

    This function creates a CSV with fixed columns (Date, Customer Phone, etc.)
    and dynamic columns based on summary artifact keys found across all logs.
    """

    summary_keys: set[str] = set()
    for log in logs:
        summary_content = get_artifact_content(log, "summary")
        if isinstance(summary_content, dict):
            summary_keys.update(summary_content.keys())

    fixed_cols = [
        "Date",
        "Transport",
        "Status",
        "Customer Phone",
        "Agent Phone",
        "Agent Name",
        "Duration",
        "User Turns",
        "Transcript",
    ]
    dynamic_cols = sorted(summary_keys)
    fieldnames = fixed_cols + dynamic_cols

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()

    for log in logs:
        writer.writerow(log_to_flat_row(log, dynamic_cols))

    return buffer.getvalue().encode("utf-8")


def log_to_flat_row(log: Log, summary_keys: list[str]) -> dict[str, Any]:
    """Convert a single log to a flattened row for CSV export."""
    participant_content = get_artifact_content(log, "participant_data") or {}
    summary_content = get_artifact_content(log, "summary") or {}
    transcript_content = get_artifact_content(log, "transcript") or {}

    participants = participant_content.get("participants", []) if isinstance(participant_content, dict) else []
    customer_phone = extract_phone_number(participants, target_role="user")
    agent_phone = extract_phone_number(participants, target_role="system")

    messages = transcript_content.get("messages", []) if isinstance(transcript_content, dict) else []
    user_turns = count_user_turns(messages)
    transcript_text = format_transcript(messages)

    session_state = log.session_state.value if hasattr(log.session_state, "value") else log.session_state

    row: dict[str, Any] = {
        "Date": format_date(log.created_at),
        "Transport": log.transport or "",
        "Status": session_state or "",
        "Customer Phone": customer_phone or "",
        "Agent Phone": agent_phone or "",
        "Agent Name": log.assistant_name or "",
        "Duration": format_duration(log.duration_seconds),
        "User Turns": user_turns,
        "Transcript": transcript_text,
    }

    for key in summary_keys:
        value = summary_content.get(key) if isinstance(summary_content, dict) else None
        if value is None:
            row[key] = ""
        elif isinstance(value, str):
            if key == "summary" and len(value) > 100:
                row[key] = value[:100] + "..."
            else:
                row[key] = value
        else:
            row[key] = json.dumps(value, ensure_ascii=False)

    return row


def get_artifact_content(log: Log, artifact_type_name: str) -> Any:
    """Extract artifact content by artifact type name."""
    for art in log.content or []:
        art_type = getattr(art, "artifact_type", None)
        art_type_value = art_type.value if hasattr(art_type, "value") else art_type
        if art_type_value == artifact_type_name:
            return getattr(art, "content", None)
    return None


def extract_phone_number(participants: list, target_role: str) -> str | None:
    """Return phone number for the participant matching the target role."""
    for participant in participants or []:
        if isinstance(participant, dict) and participant.get("role") == target_role:
            phone = participant.get("phone_number")
            if phone:
                return phone
    return None


def count_user_turns(messages: list) -> int:
    """Count how many user messages exist in the transcript."""
    return sum(1 for msg in messages or [] if isinstance(msg, dict) and msg.get("role") == "user")


def format_transcript(messages: list) -> str:
    """Format transcript messages into a readable string."""
    formatted_parts = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        text = msg.get("text") or ""
        speaker = "User" if role == "user" else "Agent"
        if text:
            formatted_parts.append(f"{speaker}: {text}")
    return " | ".join(formatted_parts)


def format_date(dt: datetime.datetime | None) -> str:
    """Format datetime as DD-Mon HH:MM."""
    if not dt:
        return ""
    return dt.strftime("%d-%b %H:%M")


def format_duration(seconds: float | None) -> str:
    """Format duration seconds as MM:SS."""
    if seconds is None:
        return ""
    total_seconds = int(round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"
