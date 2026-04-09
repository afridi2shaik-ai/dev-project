import datetime
import uuid
from enum import Enum
from typing import Any

from pydantic import Field, ConfigDict
from pydantic import BaseModel
from .base_schema import BaseSchema
from .participant_schema import ParticipantDetails
from .session_schema import SessionState


class LogType(str, Enum):
    SESSION_ARTIFACTS = "session_artifacts"
    SYSTEM_EVENT = "system_event"


class ArtifactType(str, Enum):
    SESSION_LOG = "session_log"
    HANGUP = "hangup"
    SUMMARY = "summary"
    METRICS = "metrics"
    TRANSCRIPT = "transcript"
    TRANSPORT_DETAILS = "transport_details"
    AUDIO = "audio"
    SESSION_CONTEXT = "session_context"
    SESSION_METADATA = "session_metadata"
    AGENT_CONFIGURATION = "agent_configuration"
    ERROR_DETAILS = "error_details"
    PARTICIPANT_DATA = "participant_data"
    TOOL_USAGE = "tool_usage"
    ESTIMATED_COST = "estimated_cost"
    METRICS_CSV = "metrics_csv"
    model_config = ConfigDict(
        extra="allow",  # Allow extra fields for internal operations
    )
    TURN_ANALYTICS = "turn_analytics"


class Artifact(BaseSchema):
    artifact_type: ArtifactType
    content: dict[str, Any] | str | None = None
    s3_location: str | None = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class Log(BaseSchema):
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    session_id: str
    transport: str | None = Field(None, description="The transport used for the session (e.g., 'webrtc', 'plivo').")
    assistant_id: str | None = Field(None, description="The ID of the assistant used in the session.")
    assistant_name: str | None = Field(None, description="The name of the assistant used in the session.")
    agent_type: str
    log_type: LogType
    session_state: SessionState | None = Field(None, description="The final state of the session.")
    duration_seconds: float | None = Field(None, description="The total duration of the session in seconds.")
    participants: list[ParticipantDetails] = Field(default_factory=list, description="A list of participants in the session.")
    content: list[Artifact]
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

