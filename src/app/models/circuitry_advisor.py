"""Request/response models for Circuitry advisor tool API."""


from pydantic import BaseModel, Field


class AdvisorToolRequest(BaseModel):
    """Body for POST /circuitry/advisor_tool — add Circuitry advisor tool to an agent."""

    agent_id: str = Field(..., description="Assistant/agent ID to attach the tool to")
    advisor_id: str = Field(..., description="Circuitry advisor ID (used in tool config)")

    tenant_id: str | None = Field(None, description="Tenant identifier (optional)")
    name: str | None = Field(None, description="Tool name (used only when creating a new tool)")
    description: str | None = Field(None, description="Tool description (used only when creating a new tool)")
    enabled: bool = Field(True, description="If true, enable/add the tool (default). If false, patch the tool to disabled on the agent.")

 