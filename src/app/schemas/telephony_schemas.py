import phonenumbers
from pydantic import Field, field_validator

from .base_schema import BaseSchema
from .services.agent import AgentConfig


class OutboundCallRequest(BaseSchema):
    to: str = Field(..., description="The phone number to call in E.164 format.")
    from_number: str | None = Field(None, description="The phone number to call from in E.164 format. If not provided, the default number will be used.")
    assistant_overrides: AgentConfig | None = Field(None, description="Configuration for the agent and its services.")
    assistant_id: str | None = Field(None, description="The ID of a pre-configured agent to use.")

    @field_validator("to", "from_number")
    def validate_phone_number(cls, v):
        """Validate the phone number is in E.164 format."""
        if v is None:
            return v
        try:
            phone_number = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(phone_number):
                raise ValueError("Invalid phone number format.")
        except phonenumbers.phonenumberutil.NumberParseException as e:
            raise ValueError(f"Invalid phone number: {e}")
        return v


class OutboundCallRequestNoAuth(OutboundCallRequest):
    tenant_id: str = Field(..., description="The tenant ID for which to initiate the call.")


class OutboundCallResponse(BaseSchema):
    message: str = Field(..., description="A message indicating the status of the call initiation.")
    call_id: str = Field(..., description="The unique identifier for the call.")
    session_id: str = Field(..., description="The session ID for the call.")
