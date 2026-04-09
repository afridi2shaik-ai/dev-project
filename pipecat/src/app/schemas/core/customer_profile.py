"""
Customer Profile schemas for unified user identity management.

This module provides schemas for managing customer profiles that consolidate
user information across WebRTC (email) and telephony (phone) channels.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.base_schema import BaseSchema


class LinkedIdentity(BaseSchema):
    """Represents a linked identity (email or phone) for a customer profile."""

    identity_type: Literal["email", "phone"] = Field(
        ..., description="Type of the linked identity."
    )
    value: str = Field(..., description="The identity value (email address or phone number).")
    linked_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Timestamp when this identity was linked.",
    )


class CallSummary(BaseSchema):
    """Represents a summary of a single call interaction."""

    session_id: str = Field(..., description="The session ID of the call.")
    summary_text: str = Field(..., description="AI-generated summary of the call.")
    outcome: str | None = Field(None, description="Outcome classification (e.g., 'Interested', 'Not Interested').")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="When the call occurred.",
    )
    transport_type: str = Field(..., description="Transport used for the call (webrtc, plivo, twilio, websocket).")
    duration_seconds: int | None = Field(None, description="Call duration in seconds.")


class CustomerDndAudit(BaseSchema):
    """Audit information for DND changes."""

    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="When the DND settings were last updated.",
    )
    updated_by: str | None = Field(None, description="Who updated the DND settings.")
    reason: str | None = Field(None, description="Reason for the DND update.")
    source_session_id: str | None = Field(None, description="Session that triggered the DND change.")
    source_timestamp: datetime.datetime | None = Field(None, description="Timestamp when the triggering event occurred.")


class CustomerDndTelephony(BaseSchema):
    """Telephony-specific DND settings."""

    outbound: bool = Field(False, description="Block outbound telephony calls.")
    inbound: bool = Field(False, description="Block inbound telephony calls.")


class CustomerDndChannels(BaseSchema):
    """Channel-specific DND settings."""

    telephony: CustomerDndTelephony = Field(
        default_factory=CustomerDndTelephony,
        description="Telephony DND settings."
    )


class CustomerDnd(BaseSchema):
    """Structured DND (Do Not Disturb) configuration."""

    channels: CustomerDndChannels = Field(
        default_factory=CustomerDndChannels,
        description="Channel-specific DND settings."
    )
    audit: CustomerDndAudit = Field(
        default_factory=CustomerDndAudit,
        description="Audit information for DND changes."
    )


class CustomerProfile(BaseSchema):
    """
    Unified customer profile that consolidates user information across channels.

    - For WebRTC interactions, the primary identifier is email.
    - For telephony interactions, the primary identifier is phone number.
    """

    profile_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="Unique identifier for the customer profile.",
    )
    primary_identifier: str = Field(
        ..., description="The canonical identifier used to create this profile (email or phone)."
    )
    identifier_type: Literal["email", "phone"] = Field(
        ..., description="Type of the primary identifier."
    )

    # Core user details
    name: str | None = Field(None, description="Customer's name.")
    email: str | None = Field(None, description="Customer's email address.")
    phone: str | None = Field(None, description="Customer's phone number in E.164 format.")

    # User-set preferences (manually set by user/API)
    language_preference: str | None = Field(
        None, description="User-explicitly-set preferred language code (ISO 639-1, e.g., 'en', 'hi')."
    )
    preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="User-set custom preferences (no fixed schema).",
    )

    # AI-extracted data (LLM has full control over this field)
    ai_extracted_data: dict[str, Any] = Field(
        default_factory=dict,
        description="AI-extracted data from conversations. LLM has full freedom to add any keys "
        "(name, language_preference, interests, communication_notes, etc.). "
        "This field is separate from user-set fields to allow clear distinction.",
    )

    # Identity linking
    linked_identities: list[LinkedIdentity] = Field(
        default_factory=list,
        description="Additional linked identities (email/phone) for this customer.",
    )

    # Call history (rolling window)
    recent_call_summaries: list[CallSummary] = Field(
        default_factory=list,
        description="Last 4 call summaries, newest first.",
    )
    aggregated_older_summary: str | None = Field(
        None, description="LLM-generated aggregate summary of all calls beyond the last 4."
    )
    total_call_count: int = Field(0, description="Total number of calls with this customer.")

    # DND (Do Not Disturb) settings
    dnd: CustomerDnd | None = Field(None, description="Structured DND configuration.")

    # Metadata
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="When the profile was created.",
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="When the profile was last updated.",
    )
    last_interaction_at: datetime.datetime | None = Field(
        None, description="Timestamp of the most recent call interaction."
    )

    @field_validator("language_preference")
    @classmethod
    def validate_language_code(cls, v: str | None) -> str | None:
        """Validate that language preference is a valid ISO 639-1 code."""
        if v is None:
            return v
        v = v.strip().lower()
        if len(v) < 2:
            raise ValueError("Language code must be at least 2 characters (ISO 639-1).")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str | None) -> str | None:
        """Basic phone number validation."""
        if v is None:
            return v
        v = v.strip().replace(" ", "")
        if v and not v.startswith("+"):
            v = f"+{v}"
        return v

    @field_validator("dnd")
    @classmethod
    def validate_dnd_format(cls, v: Any) -> CustomerDnd | None:
        """Reject legacy boolean dnd format."""
        if isinstance(v, bool):
            raise ValueError("Legacy dnd: bool is not supported. Use structured DND object.")
        return v


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class CustomerProfileCreateRequest(BaseSchema):
    """Request schema for creating a new customer profile."""

    primary_identifier: str = Field(
        ..., description="The primary identifier (email or phone number)."
    )
    identifier_type: Literal["email", "phone"] = Field(
        ..., description="Type of the primary identifier."
    )
    name: str | None = Field(None, description="Customer's name.")
    email: str | None = Field(None, description="Customer's email address.")
    phone: str | None = Field(None, description="Customer's phone number.")
    language_preference: str | None = Field(None, description="Preferred language code.")
    preferences: dict[str, Any] = Field(
        default_factory=dict, description="Custom preferences."
    )
    dnd: CustomerDnd | None = Field(None, description="Structured DND configuration.")

    @field_validator("primary_identifier")
    @classmethod
    def validate_primary_identifier(cls, v: str) -> str:
        """Ensure primary identifier is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("Primary identifier cannot be empty.")
        return v


class CustomerProfileUpdateRequest(BaseSchema):
    """Request schema for updating an existing customer profile."""

    name: str | None = Field(None, description="Customer's name.")
    email: str | None = Field(None, description="Customer's email address.")
    phone: str | None = Field(None, description="Customer's phone number.")
    language_preference: str | None = Field(None, description="Preferred language code.")
    preferences: dict[str, Any] | None = Field(None, description="Custom preferences to merge.")
    dnd: CustomerDnd | None = Field(None, description="Structured DND configuration.")


class LinkIdentityRequest(BaseSchema):
    """Request schema for linking an identity to a customer profile."""

    identity_type: Literal["email", "phone"] = Field(
        ..., description="Type of identity to link."
    )
    value: str = Field(..., description="The identity value to link.")

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str) -> str:
        """Ensure value is not empty."""
        v = v.strip()
        if not v:
            raise ValueError("Identity value cannot be empty.")
        return v


class CustomerProfileResponse(BaseSchema):
    """Response schema for customer profile API responses."""

    profile_id: str = Field(..., description="Unique identifier for the profile.")
    primary_identifier: str = Field(..., description="The canonical identifier.")
    identifier_type: Literal["email", "phone"] = Field(..., description="Type of primary identifier.")
    name: str | None = Field(None, description="Customer's name.")
    email: str | None = Field(None, description="Customer's email.")
    phone: str | None = Field(None, description="Customer's phone.")
    language_preference: str | None = Field(None, description="User-set preferred language.")
    preferences: dict[str, Any] = Field(default_factory=dict, description="User-set preferences.")
    ai_extracted_data: dict[str, Any] = Field(
        default_factory=dict, description="AI-extracted data from conversations."
    )
    linked_identities: list[LinkedIdentity] = Field(default_factory=list)
    recent_call_summaries: list[CallSummary] = Field(default_factory=list)
    aggregated_older_summary: str | None = Field(None)
    total_call_count: int = Field(0)
    dnd: CustomerDnd | None = Field(None, description="Structured DND configuration.")
    created_at: datetime.datetime
    updated_at: datetime.datetime
    last_interaction_at: datetime.datetime | None = None

    @classmethod
    def from_profile(cls, profile: CustomerProfile) -> "CustomerProfileResponse":
        """Create response from CustomerProfile model."""
        return cls(
            profile_id=profile.profile_id,
            primary_identifier=profile.primary_identifier,
            identifier_type=profile.identifier_type,
            name=profile.name,
            email=profile.email,
            phone=profile.phone,
            language_preference=profile.language_preference,
            preferences=profile.preferences,
            ai_extracted_data=profile.ai_extracted_data,
            linked_identities=profile.linked_identities,
            recent_call_summaries=profile.recent_call_summaries,
            aggregated_older_summary=profile.aggregated_older_summary,
            total_call_count=profile.total_call_count,
            dnd=profile.dnd,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            last_interaction_at=profile.last_interaction_at,
        )


# =============================================================================
# Path/Query Param Schemas (for dependency-driven validation)
# =============================================================================


class CustomerProfileIdentifierParams(BaseSchema):
    identifier: str = Field(..., description="Email, phone number, or profile ID.")


class CustomerProfileIdParams(BaseSchema):
    profile_id: str = Field(..., description="Profile ID.")


class CustomerProfileLinkPathParams(BaseSchema):
    profile_id: str = Field(..., description="Profile ID.")
    identity_type: Literal["email", "phone"] = Field(..., description="Identity type.")
    value: str = Field(..., description="Identity value to unlink.")


class CustomerProfileListParams(BaseSchema):
    skip: int = Field(0, ge=0, description="Number of records to skip.")
    limit: int = Field(20, ge=1, le=200, description="Maximum records to return.")
    sort_by: str = Field("last_interaction_at", description="Field to sort by.")
    sort_order: int = Field(-1, description="1 for asc, -1 for desc.")


class CustomerProfileSearchParams(BaseSchema):
    q: str = Field(..., min_length=1, description="Search query.")
    limit: int = Field(10, ge=1, le=50, description="Maximum results.")

