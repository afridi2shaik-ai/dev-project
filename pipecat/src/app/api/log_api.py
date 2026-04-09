import datetime
import io
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.api.dependencies import PaginationParams, get_db
from app.managers import LogManager
from app.schemas.log_export_schema import LogExportFormat, LogExportRequest, LogExportPreviewResponse, LogSessionStateStatsResponse
from app.schemas.log_schema import Log
from app.schemas.pagination_schema import PaginatedResponse
from app.utils.s3_utils import create_presigned_url
from app.schemas.request_params import LogParams, LogFilterParams
from app.utils.log_export_utils import logs_to_csv, logs_to_flat_csv
from app.schemas.session_schema import SessionState

log_router = APIRouter()


def _split_multi_values(values: list[str]) -> list[str]:
    """Support both repeated query params and comma-separated values."""
    out: list[str] = []
    for v in values or []:
        if v is None:
            continue
        raw = str(v).strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(",")]
        out.extend([p for p in parts if p])

    # De-dupe, preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def _parse_session_states(values: list[str]) -> list[SessionState]:
    parsed: list[SessionState] = []
    for v in values:
        try:
            parsed.append(SessionState(v))
        except Exception:
            continue

    # De-dupe, preserve order
    seen: set[SessionState] = set()
    out: list[SessionState] = []
    for s in parsed:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


async def get_log_filters(request: Request) -> LogFilterParams:
    qp = request.query_params

    user_phone_number = _split_multi_values(qp.getlist("user_phone_number"))
    customer_name = _split_multi_values(qp.getlist("customer_name"))
    agent_phone_number = _split_multi_values(qp.getlist("agent_phone_number"))

    assistant_id = _split_multi_values(qp.getlist("assistant_id"))
    assistant_name = _split_multi_values(qp.getlist("assistant_name"))
    transport = _split_multi_values(qp.getlist("transport"))
    outcome = _split_multi_values(qp.getlist("outcome"))

    session_state_raw = _split_multi_values(qp.getlist("session_state"))
    session_state = _parse_session_states(session_state_raw)

    session_id = _split_multi_values(qp.getlist("session_id"))
    q = (qp.get("q") or "").strip() or None

    # Session-state stats and list filters use start_date/end_date.
    start_date = qp.get("start_date")
    end_date = qp.get("end_date")

    return LogFilterParams(
        user_phone_number=user_phone_number or None,
        customer_name=customer_name or None,
        agent_phone_number=agent_phone_number or None,
        assistant_id=assistant_id or None,
        assistant_name=assistant_name or None,
        transport=transport or None,
        session_state=session_state or None,
        outcome=outcome or None,
        session_id=session_id or None,
        q=q,
        start_date=start_date,
        end_date=end_date,
    )


@log_router.get(
    "/stats/by-session-state",
    response_model=LogSessionStateStatsResponse,
    summary="Log counts by session_state",
)
async def logs_count_by_session_state(
    q: str | None = Query(default=None, description="Global search value."),
    start_date: str | None = Query(default=None, description="Optional start datetime/date for created_at filter."),
    end_date: str | None = Query(default=None, description="Optional end datetime/date for created_at filter."),
    db: AsyncIOMotorDatabase = Depends(get_db),
    filters: LogFilterParams = Depends(get_log_filters),
):
    """Return counts grouped by `session_state` (status). Single `$match` + `$group` aggregation.

    Same query params as `GET /logs/stats/total`. Missing `session_state` is counted under `unknown`.
    """
    # Force card filters to always honor explicit q/date params.
    effective_filters = filters.model_copy(
        update={
            "q": (q or "").strip() or None,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    manager = LogManager(db)
    total, by_session_state = await manager.count_logs_by_session_state(effective_filters)
    return LogSessionStateStatsResponse(total=total, by_session_state=by_session_state)


@log_router.get("", response_model=PaginatedResponse[Log])
async def list_logs(
    db: AsyncIOMotorDatabase = Depends(get_db),
    pagination: PaginationParams = Depends(),
    filters: LogFilterParams = Depends(get_log_filters),
):
    """List all logs with pagination and optional filtering.
    
    Query Parameters:
    - page: Page number (default: 1)
    - limit: Items per page (default: 10, max: 200)
    - user_phone_number: Filter by customer phone number(s) (repeat or comma-separated)
    - customer_name: Filter by customer name(s) (repeat or comma-separated)
    - agent_phone_number: Filter by agent/system phone number(s) (repeat or comma-separated)
    - assistant_id: Filter by assistant id(s) (repeat or comma-separated)
    - assistant_name: Filter by assistant name(s) (repeat or comma-separated)
    - transport: Filter by transport(s) (repeat or comma-separated)
    - session_state: Filter by status (repeat or comma-separated)
    - outcome: Filter by summary outcome(s) (repeat or comma-separated)
    - session_id: Filter by session id(s) (repeat or comma-separated)
    - start_date / end_date: Filter by created_at datetime range (ISO 8601 or YYYY-MM-DD)

    All filters are applied in the database before pagination (count + page slice).
    """
    manager = LogManager(db)

    logs, total_items = await manager.list_logs(
        skip=pagination.skip,
        limit=pagination.limit,
        filters=filters,
    )

    total_pages = math.ceil(total_items / pagination.limit) if pagination.limit > 0 else 0

    return PaginatedResponse(total_items=total_items, total_pages=total_pages, current_page=pagination.page, data=logs)


@log_router.get("/search", response_model=PaginatedResponse[Log])
async def search_logs(
    q: str = Query(..., min_length=2, description="Global search value"),
    start_date: str | None = Query(default=None, description="Optional start datetime/date for created_at filter."),
    end_date: str | None = Query(default=None, description="Optional end datetime/date for created_at filter."),
    session_state: SessionState | None = Query(
        default=None,
        description="Optional session_state to filter logs.",
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    """Search logs by phone/id/name with optional date range filter."""
    manager = LogManager(db)
    filters = LogFilterParams(
        q=q,
        start_date=start_date,
        end_date=end_date,
        session_state=[session_state] if session_state else None,
    )
    logs, total_items = await manager.list_logs(skip=pagination.skip, limit=pagination.limit, filters=filters)

    total_pages = math.ceil(total_items / pagination.limit) if pagination.limit > 0 else 0
    return PaginatedResponse(
        total_items=total_items,
        total_pages=total_pages,
        current_page=pagination.page,
        data=logs,
    )


@log_router.get("/{log_id}", response_model=Log)
async def get_log(params: LogParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get a single log entry by its ID."""
    manager = LogManager(db)
    log = await manager.get_log(params.log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    # Generate pre-signed URLs for artifacts with s3_location
    for artifact in log.content:
        if artifact.s3_location:
            artifact.s3_location = await create_presigned_url(artifact.s3_location)

    return log


@log_router.delete("/{log_id}", status_code=204)
async def delete_log(params: LogParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Delete a specific log entry by its ID."""
    manager = LogManager(db)
    if not await manager.delete_log(params.log_id):
        raise HTTPException(status_code=404, detail="Log not found")


@log_router.post("/export")
async def export_logs(payload: LogExportRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Export logs as CSV or JSON. With no filters, exports all logs for this service agent_type."""
    manager = LogManager(db)

    # Fetch logs with combined filters in a single database query
    logs = await manager.get_logs_with_filters(
        log_ids=payload.log_ids,
        session_ids=payload.session_ids,
        start_date=payload.start_date,
        end_date=payload.end_date,
        q=payload.q,
        session_states=[payload.session_state] if payload.session_state else None,
    )

    # Filter artifacts by requested types; keep log even if content becomes empty.
    allowed_artifacts = set(payload.artifact_types or [])
    filtered_logs: list[Log] = []
    for log in logs:
        filtered_content = []
        for art in log.content or []:
            art_type = getattr(art, "artifact_type", None)
            art_type_value = art_type.value if hasattr(art_type, "value") else art_type
            if art_type_value in allowed_artifacts:
                filtered_content.append(art)
        filtered_logs.append(log.model_copy(update={"content": filtered_content}))
    logs = filtered_logs

    exported_count = len(logs)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    if payload.format == LogExportFormat.JSON:
        file_name = f"logs-{timestamp}-{exported_count}.json"
        headers = {
            "X-Exported-Logs-Count": str(exported_count),
            "X-Exported-File-Name": file_name,
            "Content-Disposition": f'attachment; filename="{file_name}"',
        }
        body = jsonable_encoder(logs)
        return JSONResponse(content=body, headers=headers, media_type="application/json")

    if payload.format == LogExportFormat.CSV_FLAT:
        file_name = f"logs-flat-{timestamp}-{exported_count}.csv"
        headers = {
            "X-Exported-Logs-Count": str(exported_count),
            "X-Exported-File-Name": file_name,
            "Content-Disposition": f'attachment; filename="{file_name}"',
        }
        csv_bytes = logs_to_flat_csv(logs)
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="application/octet-stream",
            headers=headers,
        )

    file_name = f"logs-{timestamp}-{exported_count}.csv"
    headers = {
        "X-Exported-Logs-Count": str(exported_count),
        "X-Exported-File-Name": file_name,
        "Content-Disposition": f'attachment; filename="{file_name}"',
    }
    csv_bytes = logs_to_csv(logs)
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="application/octet-stream",
        headers=headers,
    )

@log_router.get(
    "/export/preview",
    response_model=LogExportPreviewResponse,
    summary="Preview export metadata (file name + log count)",
)
async def export_logs_preview(
    db: AsyncIOMotorDatabase = Depends(get_db),
    log_ids: list[str] | None = Query(default=None, description="Optional log IDs (repeatable)."),
    session_ids: list[str] | None = Query(default=None, description="Optional session IDs (repeatable)."),
    q: str | None = Query(default=None, description="Optional global search query used to filter logs."),
    session_state: SessionState | None = Query(
        default=None,
        description="Optional session_state to filter logs.",
    ),
    start_date: datetime.datetime | None = Query(default=None, description="Inclusive start datetime (UTC)."),
    end_date: datetime.datetime | None = Query(default=None, description="Inclusive end datetime (UTC)."),
    format: LogExportFormat = Query(default=LogExportFormat.CSV_FLAT, description="Desired export format."),
):
    """Preview export metadata without generating/downloading a file. With no query params, counts all logs for this service."""
    if (start_date and not end_date) or (end_date and not start_date):
        raise HTTPException(status_code=422, detail="Provide both start_date and end_date when filtering by date.")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date.")

    manager = LogManager(db)
    exported_count = await manager.count_logs_with_filters(
        log_ids=log_ids,
        session_ids=session_ids,
        start_date=start_date,
        end_date=end_date,
        q=q,
        session_states=[session_state] if session_state else None,
    )

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    if format == LogExportFormat.JSON:
        file_name = f"logs-{timestamp}-{exported_count}.json"
    elif format == LogExportFormat.CSV_FLAT:
        file_name = f"logs-flat-{timestamp}-{exported_count}.csv"
    else:
        file_name = f"logs-{timestamp}-{exported_count}.csv"

    applied_filters = {
        "log_ids": log_ids or None,
        "session_ids": session_ids or None,
        "q": (q or "").strip() or None,
        "session_state": session_state.value if session_state else None,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "format": format.value if hasattr(format, "value") else str(format),
    }
    return LogExportPreviewResponse(file_name=file_name, count=exported_count, applied_filters=applied_filters)
