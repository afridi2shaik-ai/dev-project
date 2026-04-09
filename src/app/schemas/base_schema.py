from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema for internal use - strict validation to catch typos."""
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra="forbid",  # Reject unknown fields to catch typos
    )
