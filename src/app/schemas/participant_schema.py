from enum import Enum

from pydantic import Field

from .base_schema import BaseSchema


class ParticipantRole(str, Enum):
    USER = "user"
    SYSTEM = "system"


class ParticipantDetails(BaseSchema):
    role: ParticipantRole = Field(..., description="The role of the participant in the call.")
    phone_number: str | None = Field(None, description="The participant's phone number in E.164 format.")
    name: str | None = Field(None, description="The participant's name.")
