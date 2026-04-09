from typing import Any

from pydantic import BaseModel, Field

KNOWN_EVENT_TYPES = frozenset({
    "session_start",
    "session_end",
    "session_artifacts_ready",
})


def validate_event_type(event_type: str) -> bool:
    """Return True if event_type is allowed."""
    return event_type in KNOWN_EVENT_TYPES


class IngestEventPayload(BaseModel):
    """Body of POST /core/events — matches what Pipecat sends."""

    event_type: str = Field(..., description="e.g. session_start, session_end, session_artifacts_ready")
    data: dict[str, Any] = Field(..., description="Session or log payload")
    timestamp: str = Field(..., description="ISO timestamp")
    tenant_id: str | None = Field(None, description="Tenant identifier")
