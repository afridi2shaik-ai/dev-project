from pydantic import BaseModel, Field

from app.schemas.session_schema import SessionState


class AssistantParams(BaseModel):
    assistant_id: str = Field(..., description="The ID of the assistant.")


class LogParams(BaseModel):
    log_id: str = Field(..., description="The ID of the log.")


class SessionParams(BaseModel):
    session_id: str = Field(..., description="The ID of the session.")


class SessionStateParams(BaseModel):
    state: SessionState | None = Field(None, description="Filter sessions by state.")


class PlivoVoiceParams(BaseModel):
    call_id: str = Field(..., description="The ID of the call from Plivo.")


class TwilioVoiceParams(BaseModel):
    call_sid: str = Field(..., description="The SID of the call from Twilio.")


class WebsocketVoiceParams(BaseModel):
    session_id: str = Field(..., description="The ID of the session for the WebSocket connection.")

class LogFilterParams(BaseModel):

    # Customer filters (from `participants` where role="user")
    user_phone_number: list[str] | None = Field(None, description="Filter by customer phone number(s).")
    customer_name: list[str] | None = Field(None, description="Filter by customer name(s) (case-insensitive, partial match).")

    # Agent/system participant filters (from `participants` where role="system")
    agent_phone_number: list[str] | None = Field(None, description="Filter by agent/system phone number(s).")

    # Assistant filters (top-level fields on `logs`)
    assistant_id: list[str] | None = Field(None, description="Filter by assistant_id(s).")
    assistant_name: list[str] | None = Field(None, description="Filter by assistant_name(s) (case-insensitive, partial match).")

    # Transport filter (top-level `transport`)
    transport: list[str] | None = Field(None, description="Filter by transport(s).")

    # Session state / status filter (top-level `session_state`)
    session_state: list[SessionState] | None = Field(None, description="Filter by session_state(s).")

    # Outcome filter (from SUMMARY artifact content.outcome)
    outcome: list[str] | None = Field(None, description="Filter by summary outcome(s).")

    # Session filter (top-level `session_id`, exact match per value)
    session_id: list[str] | None = Field(None, description="Filter by session_id(s).")
    q: str | None = Field(None, description="Global search text (phone, log/session id, or name).")

    # Date range filter (top-level `created_at`)
    start_date: str | None = Field(
        None,
        description="Filter logs by start_date >= created_from (ISO 8601 or YYYY-MM-DD). Alias: start_date.",
    )
    end_date: str | None = Field(
        None,
        description="Filter logs by end_date <= created_to (ISO 8601 or YYYY-MM-DD). Date-only values include full day. Alias: end_date.",
    )

