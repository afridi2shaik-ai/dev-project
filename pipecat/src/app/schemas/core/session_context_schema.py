import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.base_schema import BaseSchema


class TransportMode(str, Enum):
    """Types of communication transport modes."""

    WEBRTC = "webrtc"
    TWILIO = "twilio"
    PLIVO = "plivo"
    WHATSAPP = "whatsapp"
    WEBSOCKET = "websocket"
    LIVEKIT = "livekit"


class UserContextDetails(BaseSchema):
    """User-specific context information."""

    name: str | None = Field(None, description="User's display name")
    email: str | None = Field(None, description="User's email address")
    phone_number: str | None = Field(None, description="User's phone number (for phone calls)")
    user_id: str | None = Field(None, description="User's unique identifier")
    tenant_id: str = Field(..., description="Tenant/organization identifier")


class TransportContextDetails(BaseSchema):
    """Transport-specific context information."""

    mode: TransportMode = Field(..., description="The communication transport mode")
    provider_session_id: str | None = Field(None, description="Provider-specific session identifier")
    call_sid: str | None = Field(None, description="Call SID for phone calls (Twilio/Plivo)")
    from_number: str | None = Field(None, description="Caller's phone number (who initiated the call)")
    to_number: str | None = Field(None, description="Called phone number (who received the call)")
    user_phone_number: str | None = Field(None, description="User's phone number (extracted from call data)")
    agent_phone_number: str | None = Field(None, description="Agent/system phone number")
    call_direction: str | None = Field(None, description="Call direction: 'inbound' (user called us) or 'outbound' (we called user)")
    call_initiated_by: str | None = Field(None, description="Who initiated the call: 'user' or 'agent'")
    browser_info: dict[str, Any] | None = Field(None, description="Browser/device information for WebRTC")


class SessionContext(BaseSchema):
    """Complete session context that the AI can access."""

    session_id: str = Field(..., description="Unique session identifier")
    assistant_id: str | None = Field(None, description="Assistant ID for this session")
    transport: TransportContextDetails = Field(..., description="Transport-specific details")
    user: UserContextDetails = Field(..., description="User-specific details")
    conversation_metadata: dict[str, Any] = Field(default_factory=dict, description="Additional conversation metadata")
    session_start_time: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC), description="When the session started")

    def get_greeting_context(self) -> str:
        """Generate a natural greeting context string for the AI."""
        context_parts = []

        # Add transport context
        if self.transport.mode == TransportMode.WEBRTC:
            context_parts.append("via web interface")
            if self.user.name:
                context_parts.append(f"as {self.user.name}")
        elif self.transport.mode in [TransportMode.TWILIO, TransportMode.PLIVO]:
            # Provide clear context about who called whom
            if self.transport.call_direction == "inbound":
                if self.transport.user_phone_number:
                    context_parts.append(f"calling from {self.transport.user_phone_number}")
                    if self.transport.agent_phone_number:
                        context_parts.append(f"to our number {self.transport.agent_phone_number}")
                else:
                    context_parts.append("calling our phone line")
            elif self.transport.call_direction == "outbound":
                if self.transport.user_phone_number:
                    context_parts.append(f"receiving our call at {self.transport.user_phone_number}")
                    if self.transport.agent_phone_number:
                        context_parts.append(f"from our number {self.transport.agent_phone_number}")
                else:
                    context_parts.append("receiving our outbound call")
            # Fallback if direction is not clear
            elif self.transport.from_number:
                context_parts.append(f"on a phone call from {self.transport.from_number}")
            else:
                context_parts.append("via phone call")
        elif self.transport.mode == TransportMode.WHATSAPP:
            context_parts.append("via WhatsApp")

        return " ".join(context_parts) if context_parts else "via voice chat"

    def get_reference_context(self) -> str:
        """Generate context string for referencing during conversation."""
        if self.transport.mode == TransportMode.WEBRTC and self.user.name:
            return f"{self.user.name} (web interface)"
        if self.transport.mode in [TransportMode.TWILIO, TransportMode.PLIVO]:
            # More specific context for phone calls
            if self.transport.call_direction == "inbound" and self.transport.user_phone_number:
                if self.user.name:
                    return f"{self.user.name} (calling from {self.transport.user_phone_number})"
                return f"caller from {self.transport.user_phone_number}"
            if self.transport.call_direction == "outbound" and self.transport.user_phone_number:
                if self.user.name:
                    return f"{self.user.name} (at {self.transport.user_phone_number})"
                return f"customer at {self.transport.user_phone_number}"
            if self.transport.from_number:
                return f"caller from {self.transport.from_number}"

        if self.user.name:
            return self.user.name
        return "user"


class SessionContextRequest(BaseSchema):
    """Request schema for getting session context."""

    include_sensitive: bool = Field(False, description="Whether to include sensitive information like phone numbers")


class SessionContextResponse(BaseSchema):
    """Response schema for session context."""

    context: SessionContext = Field(..., description="Current session context")
    contextual_greeting: str = Field(..., description="Suggested contextual greeting")
    reference_name: str = Field(..., description="How to reference the user naturally")

