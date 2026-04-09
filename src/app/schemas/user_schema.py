from pydantic import Field, model_validator

from .base_schema import BaseSchema


class UserInfo(BaseSchema):
    id: str = Field(..., description="The unique identifier for the user (from token 'sub').")
    name: str | None = Field(None, description="The user's name.")
    email: str | None = Field(None, description="The user's email address.")
    role: str | None = Field(None, description="The user's role.")

    @model_validator(mode="before")
    @classmethod
    def handle_sub_field(cls, data):
        """Handle both 'id' and 'sub' fields from different data sources."""
        if isinstance(data, dict):
            # If 'sub' exists but 'id' doesn't, use 'sub' as 'id'
            if "sub" in data and "id" not in data:
                data["id"] = data["sub"]
        return data
