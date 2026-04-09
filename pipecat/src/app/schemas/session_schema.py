import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.base_schema import BaseSchema
from app.schemas.services.agent import AgentConfig

from .participant_schema import ParticipantDetails
from .user_schema import UserInfo


class SessionState(str, Enum):
    PREFLIGHT = "preflight"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    ERROR = "error"
    MISSED_CALL = "missed_call"  # User didn't answer outbound call
    BUSY = "busy"  # User was busy
    FAILED = "failed"  # Call failed
    VOICEMAIL = "voicemail"  # Outbound call reached voicemail/recording



class Session(BaseSchema):
    session_id: str = Field(..., alias="_id", description="The unique identifier for the session, used as the primary key.")
    agent_type: str | None = Field(None, description="The type of agent used for the session.")
    assistant_id: str | None = Field(None, description="The ID of the assistant configuration used.")
    assistant_overrides: dict[str, Any] | None = Field(None, description="The specific overrides used for this session.")
    transport: str = Field(..., description="The transport used for the session (e.g., webrtc, plivo).")
    participants: list[ParticipantDetails] = Field(default_factory=list, description="A list of participants in the session.")
    provider_session_id: str | None = Field(None, description="The session ID from the transport provider.")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="The creation time of the session.")
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="The last update time of the session.")
    end_time: datetime.datetime | None = Field(None, description="The end time of the session.")
    state: SessionState = Field(SessionState.PREFLIGHT, description="The current state of the session.")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Additional metadata for the session.")
    context_summary: dict[str, Any] | None = Field(None, description="Summary of session context (transport mode, user details available, etc.) for quick querying.")
    created_by: UserInfo | None = Field(None, description="Information about the user who created the session.")
    updated_by: UserInfo | None = Field(None, description="Information about the user who last updated the session.")


class SessionCreateRequest(BaseSchema):
    assistant_id: str | None = Field(None, description="The ID of a pre-configured agent to use.")
    assistant_overrides: AgentConfig | None = Field(None, description="Configuration overrides for the agent.")


class SessionCreateResponse(BaseSchema):
    session_id: str = Field(..., description="The unique identifier for the newly created session.")
    tenant_id: str = Field(..., description="The tenant identifier associated with the session.")
