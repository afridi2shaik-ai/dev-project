from enum import Enum

from pydantic import Field

from ..base_schema import BaseSchema
from ..core.business_tool_schema import BusinessToolReference


class FieldType(str, Enum):
    """Supported field types for API request parameters."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    URL = "url"
    DATE = "date"
    DATETIME = "datetime"


# Tool Configuration for Agent Configurations
class HangupToolConfig(BaseSchema):
    """Configuration for the hangup tool."""

    enabled: bool = Field(True, description="Whether the hangup tool is available to the assistant.")

class WarmTransferConfig(BaseSchema):
    """Configuration for the soft handover (warm transfer) tool."""

    enabled: bool = Field(False, description="Whether the warm transfer tool is available to the assistant.")
    phone_number: str | None = Field(None, description="Phone number to use for warm transfer when no agent_id/agent_name is provided. Format: +country_code_number (e.g., +1234567890)")
    transfer_prompt: str = Field(
        "Sure, let me connect you to one of our representatives. Please hold for a moment.",
        description="Prompt spoken to the user before starting the transfer workflow.",
    )
    max_transfer_attempts: int = Field(
        3, description="Maximum number of attempts to connect with the target supervisor/agent."
    )


class CallSchedulerToolConfig(BaseSchema):
    """Configuration for the call scheduler tool."""

    enabled: bool = Field(True, description="Whether the call scheduler tool is available to the assistant.")

class RagToolConfig(BaseSchema):
    enabled: bool =Field(True,description="Whether the rag tool(Knowledge Center ) is available to the assistant.")


class CrmToolConfig(BaseSchema):
    """Built-in CRM MCP integration. Pipecat env ``CRM_MCP_URL`` is the CRM API base (e.g. https://host/crm-api); /mcp/stream is appended."""

    enabled: bool = Field(
        False,
        description="When true, register CRM MCP using CRM_MCP_URL base + /mcp/stream.",
    )


class ToolsConfig(BaseSchema):
    """Configuration for tools available to the assistant."""

    hangup_tool: HangupToolConfig | None = Field(None, description="Configuration for the hangup tool.")
    Warm_transfer_tool: WarmTransferConfig | None = Field(None, description="Configuration for the soft handover (warm transfer) tool.")
    call_scheduler_tool: CallSchedulerToolConfig | None = Field(default_factory=CallSchedulerToolConfig, description="Configuration for the call scheduler tool.")
    rag_tool:RagToolConfig |None =Field(None,disription="Configuration for the rag tool.")
    business_tools: list[BusinessToolReference] = Field(default_factory=list, description="List of business tool references with their enablement status.")
    crm: CrmToolConfig | None = Field(
        None,
        description='CRM MCP: set CRM_MCP_URL to API base (e.g. https://host/crm-api). Example: {"enabled": true}.',
    )

