import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import PaginationParams, get_current_user, get_db, get_http_client
from app.managers import LogManager, SessionManager
from app.schemas.api_schema import Artifact, SessionLogsResponse
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.request_params import SessionParams, SessionStateParams
from app.schemas.session_schema import Session, SessionCreateRequest, SessionCreateResponse
from app.schemas.user_schema import UserInfo
from app.services.assistant_api_client import AssistantAPIClient, AssistantAPINotFound, AssistantAPIError
from app.services.token_provider import TokenProvider
from app.utils.s3_utils import create_presigned_url

session_router = APIRouter()


@session_router.post("", response_model=SessionCreateResponse)
async def create_session(
    request: SessionCreateRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    http_client = Depends(get_http_client),
):
    """Create a new session and store agent configuration."""
    session_manager = SessionManager(db)

    assistant_id = request.assistant_id or "default"

    # Validate assistant exists (skip validation for "default" assistant)
    if assistant_id != "default":
        try:
            # Extract tokens from request for assistant API call
            try:
                access_token, id_token = TokenProvider.get_tokens_from_request(http_request)
            except ValueError:
                # If tokens not available in request, try to get from current_user or use token provider
                # For now, raise error if tokens not available
                raise HTTPException(
                    status_code=400,
                    detail="Authorization and id_token headers are required to validate assistant",
                )

            # Validate assistant exists by attempting to fetch its config
            assistant_client = AssistantAPIClient()
            try:
                await assistant_client.get_config(
                    assistant_id=assistant_id,
                    access_token=access_token,
                    id_token=id_token,
                    session=http_client,
                )
            except AssistantAPINotFound:
                raise HTTPException(
                    status_code=404,
                    detail=f"Assistant '{assistant_id}' not found",
                )
            except AssistantAPIError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to validate assistant: {str(e)}",
                )
        except HTTPException:
            raise
        except Exception as e:
            # Log unexpected errors but don't fail session creation
            from loguru import logger
            logger.warning(f"Failed to validate assistant {assistant_id}: {e}")

    overrides_dict = request.assistant_overrides.model_dump(exclude_unset=True) if request.assistant_overrides else None

    user_info = UserInfo(id=current_user.get("sub"), name=current_user.get("name"), email=current_user.get("email"), role=current_user.get("role"))

    session_id = str(uuid.uuid4())
    try:
        await session_manager.create_session(session_id=session_id, assistant_id=assistant_id, assistant_overrides=overrides_dict, created_by=user_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SessionCreateResponse(session_id=session_id, tenant_id=db.name)


@session_router.get("", response_model=PaginatedResponse[Session])
async def list_sessions(db: AsyncIOMotorDatabase = Depends(get_db), pagination: PaginationParams = Depends(), state_params: SessionStateParams = Depends()):
    """List all sessions with pagination and filtering."""
    manager = SessionManager(db)
    sessions, total_items = await manager.list_sessions(skip=pagination.skip, limit=pagination.limit, state=state_params.state)

    total_pages = math.ceil(total_items / pagination.limit) if pagination.limit > 0 else 0

    return PaginatedResponse(total_items=total_items, total_pages=total_pages, current_page=pagination.page, data=sessions)


@session_router.get("/{session_id}", response_model=Session)
async def get_session(params: SessionParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get detailed information about a specific session."""
    manager = SessionManager(db)
    session = await manager.get_session(params.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@session_router.get("/{session_id}/logs", response_model=SessionLogsResponse)
async def get_session_logs(params: SessionParams = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get all logs and artifacts associated with a specific session."""
    session_manager = SessionManager(db)
    session = await session_manager.get_session(params.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    log_manager = LogManager(db)
    logs = await log_manager.get_logs_for_session(params.session_id)

    artifacts = []
    # Assuming one log document per session as per the new design
    if logs and logs[0].content:
        for artifact_data in logs[0].content:
            artifact_dict = artifact_data.model_dump()
            if artifact_dict.get("s3_location"):
                artifact_dict["s3_location"] = await create_presigned_url(artifact_dict["s3_location"])
            artifacts.append(Artifact(**artifact_dict))

    return SessionLogsResponse(session_id=session.session_id, created_at=session.created_at, artifacts=artifacts)
