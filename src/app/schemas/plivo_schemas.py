from pydantic import Field

from .base_schema import BaseSchema

# --- API Response Schemas ---


class PlivoApplication(BaseSchema):
    app_id: str = Field(..., description="The unique ID of the Plivo application.")
    app_name: str = Field(..., description="The friendly name of the application.")
    answer_url: str | None = Field(None, description="The URL Plivo will request when a call is answered.")
    hangup_url: str | None = Field(None, description="The URL Plivo will request when a call is hung up.")


class PlivoNumber(BaseSchema):
    number: str = Field(..., description="The phone number in E.164 format.")
    app_id: str | None = Field(None, description="The ID of the application linked to this number.")
    alias: str = Field(..., description="The friendly name for the number.")


# --- API Request Schemas ---


class UpdatePlivoApplicationRequest(BaseSchema):
    answer_url: str = Field(..., description="The new Answer URL to set for the application. This should point to the server's inbound webhook.")


class AssignAppToNumberRequest(BaseSchema):
    app_id: str = Field(..., description="The ID of the application to link to the phone number.")
