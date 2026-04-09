import logging

from fastapi import APIRouter, HTTPException, Request

from app.client_api.circuitry.client import (
    build_patch_usage_payload,
    build_post_usage_payload,
    patch_circuitry_usage,
    post_circuitry_usage_and_return_id,
)
from app.auth0.auth_service import AuthService
from app.core.config import AUTH_ENABLED, ADVANCE_LOGS
from app.models.event import IngestEventPayload, validate_event_type

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache: log_id -> Circuitry usage_id (from POST response). Used to send correct aiworker_usage_id on PATCH.
_circuitry_usage_id_by_log_id: dict[str, str] = {}


@router.post("/events")
async def ingest_event(request: Request, payload: IngestEventPayload):
    """
    Receive events from Pipecat.
    Body: event_type, data, timestamp, tenant_id.
    """
    id_token = request.headers.get("id_token") or request.headers.get("x-id-token")
    if AUTH_ENABLED:
        if id_token:
            # Accept both raw JWT and "Bearer <jwt>" for compatibility.
            token_value = id_token.split("Bearer ")[-1].strip()
            decoded = AuthService.decode_id_token(token_value)
            token_tenant_id = decoded.get("tenant_id")

            if not token_tenant_id:
                raise HTTPException(status_code=401, detail="tenant_id missing in id_token")
            if not payload.tenant_id:
                raise HTTPException(status_code=400, detail="tenant_id missing in payload")
            if token_tenant_id != payload.tenant_id:
                raise HTTPException(status_code=403, detail="tenant_id mismatch between token and payload")
        else:
            raise HTTPException(status_code=401, detail="id_token header is required")

    if not validate_event_type(payload.event_type):
        raise HTTPException(status_code=400, detail=f"Unknown event_type: {payload.event_type}")

    data = payload.data or {}
    session_id = data.get("session_id") or data.get("_id")
    logger.info(
        "Ingest | event_type=%s | tenant_id=%s | session_id=%s",
        payload.event_type,
        payload.tenant_id,
        session_id,
    )
    if ADVANCE_LOGS:
        logger.info("Ingest payload received (event-management): %s", payload.model_dump(mode="json"))

    if payload.event_type == "session_start":
        post_payload = build_post_usage_payload(data, payload.tenant_id)
        circuitry_usage_id = post_circuitry_usage_and_return_id(post_payload, tenant_id=payload.tenant_id)
        log_id = (
            data.get("log_id")
            or (data.get("updated_by") or {}).get("log_id")
            or (data.get("created_by") or {}).get("log_id")
        )
        if log_id and circuitry_usage_id:
            _circuitry_usage_id_by_log_id[log_id] = circuitry_usage_id
    elif payload.event_type == "session_end":
        # Do not PATCH or pop here; wait for session_artifacts_ready so PATCH uses final Call JSON (session_state).
        pass
    elif payload.event_type == "session_artifacts_ready":
        log_id = data.get("log_id") or data.get("_id") or ""
        # Always pass log_id to Circuitry PATCH (do not override with Circuitry's returned id)
        usage_id = log_id
        _circuitry_usage_id_by_log_id.pop(log_id, None)  # cleanup cache if present
        created_by = data.get("created_by")
        executed_by = created_by.get("id") if isinstance(created_by, dict) and created_by.get("id") else None
        if not executed_by and data.get("content"):
            for art in data.get("content") or []:
                if isinstance(art, dict) and art.get("artifact_type") == "participant_data":
                    cb = (art.get("content") or {}).get("created_by") if isinstance(art.get("content"), dict) else None
                    if isinstance(cb, dict) and cb.get("id"):
                        executed_by = cb["id"]
                        break
        patch_payload = build_patch_usage_payload(
            aiworker_usage_id=usage_id,
            tenant_id=payload.tenant_id or "",
            agent_score="NA",
            status="succeeded",
            tags=[{"key": "typee", "value": "Call Record"}],
            executed_by=executed_by,
        )
        patch_circuitry_usage(patch_payload, tenant_id=payload.tenant_id)

    return {"status": "ok", "event_type": payload.event_type, "session_id": session_id}
