import datetime
from typing import Any

from pydantic import Field

from .base_schema import BaseSchema
from .log_schema import ArtifactType


class Artifact(BaseSchema):
    artifact_type: ArtifactType = Field(..., description="The type of artifact.")
    content: dict[str, Any] | str | None = Field(None, description="The content of the artifact.")
    s3_location: str | None = Field(None, description="The path to the artifact in S3.")
    created_at: datetime.datetime = Field(..., description="The creation time of the artifact.")


class SessionLogsResponse(BaseSchema):
    session_id: str = Field(..., description="The session these logs belong to.")
    created_at: datetime.datetime = Field(..., description="The creation time of the session.")
    artifacts: list[Artifact] = Field(..., description="A list of all artifacts for the session.")


class PresignedUrlRequest(BaseSchema):
    s3_path: str = Field(..., description="The full S3 path (key) of the artifact to be accessed.")


class PresignedUrlResponse(BaseSchema):
    url: str = Field(..., description="The temporary, pre-signed URL to access the artifact.")
