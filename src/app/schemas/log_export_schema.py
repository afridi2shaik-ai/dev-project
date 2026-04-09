import datetime
from enum import Enum
from typing import ClassVar
from pydantic import BaseModel
from pydantic import Field, model_validator

from .base_schema import BaseSchema
from .session_schema import SessionState


class LogExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    CSV_FLAT = "csv_flat"


class LogExportRequest(BaseSchema):
    """Request schema for exporting logs in bulk."""

    DEFAULT_ARTIFACT_TYPES: ClassVar[list[str]] = ["participant_data", "summary","transcript"]
    MAX_ARTIFACT_TYPES: ClassVar[int] = 50
    log_ids: list[str] | None = Field(
        default=None, description="Optional log IDs to export. Omit (with no other filters) to export all logs for this service."
    )
    session_ids: list[str] | None = Field(
        default=None, description="Optional session IDs whose logs should be exported. Omit (with no other filters) to export all logs for this service."
    )
    q: str | None = Field(
        default=None, description="Optional global search query (phone/id/name) used to filter logs."
    )
    session_state: SessionState | None = Field(
        default=None,
        description="Optional session_state to filter logs.",
    )
    start_date: datetime.datetime | None = Field(
        default=None,
        description="Inclusive start datetime (UTC) for filtering logs by created_at."
    )
    end_date: datetime.datetime | None = Field(
        default=None,
        description="Inclusive end datetime (UTC) for filtering logs by created_at."
    )
    format: LogExportFormat = Field(
        default=LogExportFormat.CSV_FLAT, description="Desired export format (csv or json). csv_flat is a flat csv with all the artifacts in a single row."
    )
    artifact_types: list[str] = Field(
        default_factory=lambda: LogExportRequest.DEFAULT_ARTIFACT_TYPES.copy(),
        description="Artifact types to include. Defaults to participant_data, summary and transcript. example: ['participant_data', 'summary', 'transcript']",
    )

    # NOTE: Export item limits are intentionally not enforced here.
    # The export endpoint is expected to handle large exports operationally.
    MAX_ITEMS: ClassVar[int | None] = None

    @model_validator(mode="after")
    def _validate_selection(self):
        log_ids = list(dict.fromkeys(self.log_ids or []))
        session_ids = list(dict.fromkeys(self.session_ids or []))
        artifact_types = list(dict.fromkeys(self.artifact_types or []))
        session_state = self.session_state
        start_date = self.start_date
        end_date = self.end_date
        q = (self.q or "").strip()

        if (start_date and not end_date) or (end_date and not start_date):
            raise ValueError("Provide both start_date and end_date when filtering by date.")

        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")

        total_requested = len(log_ids) + len(session_ids)
        if self.MAX_ITEMS is not None and total_requested > self.MAX_ITEMS:
            raise ValueError(f"Too many identifiers provided. Max allowed is {self.MAX_ITEMS}.")

        if not artifact_types:
            artifact_types = self.DEFAULT_ARTIFACT_TYPES.copy()
        if len(artifact_types) > self.MAX_ARTIFACT_TYPES:
            raise ValueError(
                f"Too many artifact_types provided. Max allowed is {self.MAX_ARTIFACT_TYPES}."
            )

        # Assign the de-duplicated lists back
        self.log_ids = log_ids or None
        self.session_ids = session_ids or None
        self.q = q or None
        self.session_state = session_state or None
        self.artifact_types = artifact_types
        return self


class LogExportPreviewResponse(BaseModel):
    file_name: str = Field(..., description="Generated export file name (for display).")
    count: int = Field(..., description="Total logs included in the export.")
    applied_filters: dict = Field(..., description="Filters applied to produce this preview count.")

class LogSessionStateStatsResponse(BaseModel):
    total: int = Field(..., description="Number of log documents matching the optional filters.")
    by_session_state: dict[str, int] = Field(
        ...,
        description="Counts grouped by top-level session_state (missing/null stored as 'unknown').",
    )