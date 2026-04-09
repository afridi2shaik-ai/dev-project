import logging
from datetime import datetime

import requests

from ...core.config import CIRCUITRY_API_BASE_URL, ADVANCE_LOGS
from .tokens import get_circuitry_token

logger = logging.getLogger(__name__)

CIRCUITRY_USAGE_URL = f"{CIRCUITRY_API_BASE_URL}/v1/aiworkers/usage"


def _format_used_at(created_at: str | None) -> str:
    """Format created_at for Circuitry used_at (%Y-%m-%dT%H:%M:%S.%f, no Z)."""
    if not created_at or not isinstance(created_at, str):
        return ""
    s = created_at.strip().rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    except (ValueError, TypeError):
        if not s:
            return ""
        s = s.replace(" ", "T", 1)[:26]
        return s if "." in s else s + ".000000"


def build_post_usage_payload(data: dict, tenant_id: str | None) -> dict:
    """Build POST body for aiworkers/usage from session_start (Pipecat Session payload).

    Maps: assistant_id -> aiworker_id, created_at -> used_at, created_by.id -> executed_by,
    session_state -> status. Keeps aiworker_type as "conversations"; input_data sent empty.
    Sends log_id as aiworker_usage_id when present (Pipecat sends log_id at session_start).
    """
    payload = {
        "aiworker_id": data.get("assistant_id") or "36113f08-cc53-4fed-977a-e67f5383b9d5",
        "aiworker_type": "action_logs",
        "used_at": _format_used_at(data.get("created_at")),
        "status": data.get("session_state") or "in_progress",
        "input_data": {},
    }
    created_by = data.get("created_by")
    if isinstance(created_by, dict) and created_by.get("id"):
        payload["executed_by"] = created_by["id"]
    log_id = (
        data.get("log_id")
        or (data.get("updated_by") or {}).get("log_id")
        or (data.get("created_by") or {}).get("log_id")
    )
    if log_id:
        payload["aiworker_usage_id"] = log_id
    return payload


def _format_tenant_id_with_hyphens(tenant_id: str) -> str:
    """Format tenant_id for Circuitry PATCH: 32 hex chars -> xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx."""
    if not tenant_id or not isinstance(tenant_id, str):
        return tenant_id or ""
    s = tenant_id.strip().replace("-", "")
    if len(s) == 32 and all(c in "0123456789abcdefABCDEF" for c in s):
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}".lower()
    return tenant_id


def build_patch_usage_payload(
    aiworker_usage_id: str,
    tenant_id: str,
    agent_score: str = "NA",
    status: str = "succeeded",
    tags: list | None = None,
    executed_by: str | None = None,
) -> dict:
    """Build PATCH body with aiworker_usage_id (singular), agent_score, tenant_id, status, tags, optional executed_by."""
    default_tags = [{"key": "typee", "value": "Call Record"}]
    payload = {
        "aiworker_usage_id": aiworker_usage_id,
        "agent_score": agent_score,
        "tenant_id": _format_tenant_id_with_hyphens(tenant_id),
        "status": status,
        "tags": tags if tags is not None else default_tags,
    }
    if executed_by:
        payload["executed_by"] = executed_by
    return payload


def _headers_with_token(tenant_id: str | None = None):
    """Get token (using tenant_id from ingest when provided) and return headers."""
   # tenant_id="e93fcee5bbd853539fcd78751463849a"
    token = get_circuitry_token(tenant_id)
    if not token:
        return None
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def post_circuitry_usage_and_return_id(payload: dict, tenant_id: str | None = None) -> str | None:
    """POST to Circuitry aiworkers/usage; returns usage_id on success (200), None otherwise."""
    headers = _headers_with_token(tenant_id)
    if not headers:
        logger.warning("Circuitry usage: no token, skipping POST")
        return None
    try:
        if ADVANCE_LOGS:
            logger.info("Circuitry usage POST payload (before send): %s", payload)
        resp = requests.post(CIRCUITRY_USAGE_URL, json=payload, headers=headers, timeout=10)
        body = resp.json() if resp.content else {}
        if not isinstance(body, dict):
            body = {}
        status_code = body.get("status_code") or getattr(resp, "status_code", None)
        message = body.get("message", "")
        data = body.get("data")
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            usage_id = data[0].get("id")
        else:
            usage_id = body.get("_id") or body.get("id") if isinstance(body, dict) else None
        if ADVANCE_LOGS:
            logger.info("Circuitry usage POST: status_code=%s message=%s usage_id=%s", status_code, message, usage_id)
        else:
            logger.info("Circuitry POST: status_code=%s", status_code)
        return usage_id if status_code == 200 else None
    except requests.RequestException as e:
        logger.warning("Circuitry usage: POST failed %s", e)
        return None


def patch_circuitry_usage(payload: dict, tenant_id: str | None = None) -> None:
    """PATCH to Circuitry aiworkers/usage (e.g. session_end). Logs status_code, message in client only."""
    headers = _headers_with_token(tenant_id)
    if not headers:
        logger.warning("Circuitry usage: no token, skipping PATCH")
        return
    try:
        if ADVANCE_LOGS:
            logger.info("Circuitry usage PATCH payload (before send): %s", payload)
        resp = requests.patch(CIRCUITRY_USAGE_URL, json=payload, headers=headers, timeout=10)
        body = resp.json() if resp.content else {}
        if not isinstance(body, dict):
            body = {}
        status_code = body.get("status_code") or getattr(resp, "status_code", None)
        message = body.get("message", "")
        if ADVANCE_LOGS:
            logger.info("Circuitry usage PATCH: status_code=%s message=%s", status_code, message)
        else:
            logger.info("Circuitry PATCH: status_code=%s", status_code)
    except requests.RequestException as e:
        logger.warning("Circuitry usage: PATCH failed %s", e)
