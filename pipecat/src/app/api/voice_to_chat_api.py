"""
Voice-to-chat API: create a WebRTC session for continuous voice in, text out.

Creates a session with pipeline_mode: audio_chat (and any other overrides),
returns session_id and offer endpoint so the widget can connect via WebRTC
and receive continuous chat (text) responses.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import get_current_user, get_db, get_http_client
from app.managers.session_manager import SessionManager
from app.schemas.session_schema import SessionCreateRequest
from app.schemas.user_schema import UserInfo
from app.schemas.voice_to_chat_schema import VoiceToChatResponse
from app.services.assistant_api_client import AssistantAPIClient, AssistantAPINotFound, AssistantAPIError
from app.services.token_provider import TokenProvider

voice_to_chat_router = APIRouter()

def _merge_overrides(user_overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user overrides and force pipeline_mode to audio_chat for this endpoint."""
    merged = dict(user_overrides) if user_overrides else {}
    merged["pipeline_mode"] = "audio_chat"
    return merged


@voice_to_chat_router.post(
    "/voice-to-chat",
    response_model=VoiceToChatResponse,
    summary="Start voice-to-chat session",
    description="Create a session for WebRTC voice-to-chat (continuous voice in, text out). Returns session_id and offer endpoint for the widget.",
)
async def voice_to_chat(
    request: Request,
    body: SessionCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    http_client=Depends(get_http_client),
):
    """Create a session with pipeline_mode: audio_chat and return connection info for WebRTC."""
    session_manager = SessionManager(db)
    assistant_id = body.assistant_id or "default"

    # Validate assistant if not default (same as session_api)
    if assistant_id != "default":
        try:
            try:
                access_token, id_token = TokenProvider.get_tokens_from_request(request)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Authorization and id_token headers are required to validate assistant",
                )
            assistant_client = AssistantAPIClient()
            try:
                await assistant_client.get_config(
                    assistant_id=assistant_id,
                    access_token=access_token,
                    id_token=id_token,
                    session=http_client,
                )
            except AssistantAPINotFound:
                raise HTTPException(status_code=404, detail=f"Assistant '{assistant_id}' not found")
            except AssistantAPIError as e:
                raise HTTPException(status_code=500, detail=f"Failed to validate assistant: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to validate assistant {assistant_id}: {e}")

    # Build overrides: ensure pipeline_mode is audio_chat, merge with user overrides
    user_overrides = body.assistant_overrides.model_dump(exclude_unset=True) if body.assistant_overrides else None
    overrides_dict = _merge_overrides(user_overrides)

    # Create session via SessionManager (expects dict overrides; we need to pass merged dict)
    # SessionManager.create_session expects assistant_overrides as dict
    user_info = UserInfo(
        id=current_user.get("sub"),
        name=current_user.get("name"),
        email=current_user.get("email"),
        role=current_user.get("role"),
    )
    session_id = str(uuid.uuid4())
    try:
        await session_manager.create_session(
            session_id=session_id,
            assistant_id=assistant_id,
            assistant_overrides=overrides_dict,
            created_by=user_info,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Build offer URL (widget will POST here with session_id and SDP)
    base = request.base_url
    offer_path = "/vagent/api/offer"
    offer_endpoint = f"{base.scheme}://{base.netloc.rstrip('/')}{offer_path}"

    return VoiceToChatResponse(
        session_id=session_id,
        tenant_id=db.name,
        offer_endpoint=offer_endpoint,
        message="Use session_id with POST /vagent/api/offer (body: session_id, sdp, type) to start WebRTC. Pipeline is audio_chat: voice in, text out.",
    )
