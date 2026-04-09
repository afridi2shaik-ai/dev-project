"""Schemas for the voice-to-chat API (WebRTC session for continuous voice in, text out)."""

from pydantic import Field

from app.schemas.base_schema import BaseSchema


class VoiceToChatResponse(BaseSchema):
    """Response for POST /voice-to-chat: session and connection info for WebRTC widget."""

    session_id: str = Field(..., description="Session ID to use with POST /vagent/api/offer.")
    tenant_id: str = Field(..., description="Tenant ID for the session.")
    offer_endpoint: str = Field(
        ...,
        description="Full URL for WebRTC offer: POST this with session_id and SDP to connect.",
    )
    message: str = Field(
        default="Use session_id with POST /vagent/api/offer (body: session_id, sdp, type) to start WebRTC. Pipeline is audio_chat: voice in, text out.",
        description="Instructions for the widget.",
    )
