from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.services.agent import AgentConfig


class StrictAPISchema(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra="forbid",
    )


class AssistantAPIResponse(StrictAPISchema):
    tenant_id: str = Field(..., description="Tenant identifier from API response")
    assistant_id: str = Field(..., description="Assistant identifier from API response")
    config: AgentConfig = Field(..., description="Complete assistant configuration matching AgentConfig schema")


class AssistantValidationRequest(BaseModel):
    """Request schema for assistant validation endpoint."""

    config: dict[str, Any] = Field(..., description="Assistant configuration to validate")


class AssistantValidationResponse(BaseModel):
    """Response schema for assistant validation endpoint."""

    valid: bool = Field(..., description="Whether the payload is valid")
    errors: list[str] = Field(default_factory=list, description="List of validation error messages (if invalid)")
    validated_config: dict[str, Any] | None = Field(None, description="Validated config object as dict (if valid)")
