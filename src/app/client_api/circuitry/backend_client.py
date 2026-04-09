"""
Backend / Assistant API client (circuitry flow).

Calls the backend to GET and PATCH agent config (add tool to agent).
Uses /api/agent/{id} which supports GET and PATCH; /api/agentcall/assistants/{id} is GET-only.
"""

import logging
from typing import Any

import requests

from app.core.config import BACKEND_ASSISTANT_API_BASE_URL

logger = logging.getLogger(__name__)

# Agent config API: GET and PATCH are on /api/agent/{assistant_id} (lead-management agent_router).
ASSISTANT_PATH = "/api/agent"


def _backend_headers(token_value: str | None) -> dict[str, str]:
    """Build common headers for backend assistant API calls."""
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["id_token"] = token_value
    return headers


def get_agent(
    agent_id: str,
    token_value: str | None,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    GET agent config from backend.

    Args:
        agent_id: Assistant/agent ID.
        token_value: JWT for Authorization and id_token headers (optional).
        timeout: Request timeout in seconds.

    Returns:
        Full agent response JSON on success, or dict with "error" key on failure.
    """
    if not BACKEND_ASSISTANT_API_BASE_URL:
        logger.warning("BACKEND_ASSISTANT_API_BASE_URL not set, skipping get agent")
        return {"error": "BACKEND_ASSISTANT_API_BASE_URL not set"}

    base = BACKEND_ASSISTANT_API_BASE_URL.rstrip("/")
    url = f"{base}{ASSISTANT_PATH}/{agent_id}"
    headers = _backend_headers(token_value)

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            err = resp.text or f"GET agent {resp.status_code}"
            logger.warning("Backend GET agent failed: %s", err)
            return {"error": err}
        data = resp.json() if resp.content else {}
        return data
    except requests.RequestException as e:
        logger.warning("Backend agent request failed: %s", e)
        return {"error": str(e)}


def list_agents(
    token_value: str | None,
    skip: int = 0,
    limit: int = 100,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    GET paginated agent list from backend (same service as get_agent).

    Returns:
        On success: {"data": [...], "total_items": int}
        On failure: {"error": str}
    """
    if not BACKEND_ASSISTANT_API_BASE_URL:
        logger.warning("BACKEND_ASSISTANT_API_BASE_URL not set, skipping list agents")
        return {"error": "BACKEND_ASSISTANT_API_BASE_URL not set"}

    base = BACKEND_ASSISTANT_API_BASE_URL.rstrip("/")
    url = f"{base}{ASSISTANT_PATH}"
    headers = _backend_headers(token_value)

    try:
        resp = requests.get(
            url,
            params={"skip": skip, "limit": limit},
            headers=headers,
            timeout=timeout,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code != 200:
            err = (data.get("detail") if isinstance(data, dict) else None) or resp.text or f"LIST agents {resp.status_code}"
            logger.warning("Backend LIST agents failed: %s", err)
            return {"error": str(err)}
        return data if isinstance(data, dict) else {"error": "Invalid JSON"}
    except requests.RequestException as e:
        logger.warning("Backend list agents request failed: %s", e)
        return {"error": str(e)}


def patch_agent_add_tool(
    agent_id: str,
    tool_id: str,
    token_value: str | None,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    GET agent config from backend, add tool_id to tools.business_tools, PATCH back.

    Args:
        agent_id: Assistant/agent ID.
        tool_id: Business tool ID to add.
        token_value: JWT for Authorization and id_token headers (optional).
        timeout: Request timeout in seconds.

    Returns:
        Dict with "success": True and optional "message", or "error" key on failure.
    """
    get_result = get_agent(agent_id, token_value, timeout)
    if "error" in get_result:
        return get_result

    # GET /api/agent/{id} returns the config at top level (AgentConfig); some backends may wrap in "config".
    config = get_result.get("config") if isinstance(get_result.get("config"), dict) else (get_result if isinstance(get_result, dict) else None)
    if not config:
        logger.warning("Backend agent response missing or invalid config")
        return {"error": "Agent config missing or invalid"}

    if not BACKEND_ASSISTANT_API_BASE_URL:
        return {"error": "BACKEND_ASSISTANT_API_BASE_URL not set"}
    base = BACKEND_ASSISTANT_API_BASE_URL.rstrip("/")
    url = f"{base}{ASSISTANT_PATH}/{agent_id}"
    headers = _backend_headers(token_value)

    tools = config.get("tools") or {}
    if not isinstance(tools, dict):
        tools = {}
    business_tools = list(tools.get("business_tools") or [])
    if not isinstance(business_tools, list):
        business_tools = []

    found = False
    already_enabled = False
    for entry in business_tools:
        if isinstance(entry, dict) and str(entry.get("tool_id")) == str(tool_id):
            found = True
            if entry.get("enabled") is True:
                already_enabled = True
            else:
                entry["enabled"] = True
            break
    if already_enabled:
        logger.info("Tool already enabled on agent: agent_id=%s tool_id=%s", agent_id, tool_id)
        return {"success": True, "message": "Tool already enabled on agent"}
    if not found:
        business_tools.append({"tool_id": tool_id, "enabled": True})

    tools["business_tools"] = business_tools
    # PATCH /api/agent/{id} expects partial update (e.g. {"tools": {...}}), not {"config": ...}.
    patch_body = {"tools": tools}

    try:
        patch_resp = requests.patch(url, json=patch_body, headers=headers, timeout=timeout)
        if patch_resp.status_code not in (200, 204):
            err = patch_resp.text or f"PATCH agent {patch_resp.status_code}"
            logger.warning("Backend PATCH agent failed: %s", err)
            return {"error": err}
        msg = "Tool enabled on agent" if found else "Tool added to agent"
        logger.info("Backend patch agent success: agent_id=%s tool_id=%s", agent_id, tool_id)
        return {"success": True, "message": msg}
    except requests.RequestException as e:
        logger.warning("Backend agent request failed: %s", e)
        return {"error": str(e)}


def patch_agent_set_tool_enabled(
    agent_id: str,
    tool_id: str,
    enabled: bool,
    token_value: str | None,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    GET agent config, set the given tool_id's enabled flag in tools.business_tools, PATCH back.

    If the tool_id is not in the agent's business_tools list, it is added with the given enabled value.

    Args:
        agent_id: Assistant/agent ID.
        tool_id: Business tool ID to update.
        enabled: Whether the tool should be enabled.
        token_value: JWT for Authorization and id_token headers (optional).
        timeout: Request timeout in seconds.

    Returns:
        Dict with "success": True and optional "message", or "error" key on failure.
    """
    get_result = get_agent(agent_id, token_value, timeout)
    if "error" in get_result:
        return get_result

    # GET /api/agent/{id} returns the config at top level (AgentConfig); some backends may wrap in "config".
    config = get_result.get("config") if isinstance(get_result.get("config"), dict) else (get_result if isinstance(get_result, dict) else None)
    if not config:
        logger.warning("Backend agent response missing or invalid config")
        return {"error": "Agent config missing or invalid"}

    if not BACKEND_ASSISTANT_API_BASE_URL:
        return {"error": "BACKEND_ASSISTANT_API_BASE_URL not set"}
    base = BACKEND_ASSISTANT_API_BASE_URL.rstrip("/")
    url = f"{base}{ASSISTANT_PATH}/{agent_id}"
    headers = _backend_headers(token_value)

    tools = config.get("tools") or {}
    if not isinstance(tools, dict):
        tools = {}
    business_tools = list(tools.get("business_tools") or [])
    if not isinstance(business_tools, list):
        business_tools = []

    found = False
    for entry in business_tools:
        if isinstance(entry, dict) and str(entry.get("tool_id")) == str(tool_id):
            entry["enabled"] = enabled
            found = True
            break
    if not found:
        business_tools.append({"tool_id": tool_id, "enabled": enabled})

    tools["business_tools"] = business_tools
    # PATCH /api/agent/{id} expects partial update (e.g. {"tools": {...}}), not {"config": ...}.
    patch_body = {"tools": tools}

    try:
        patch_resp = requests.patch(url, json=patch_body, headers=headers, timeout=timeout)
        if patch_resp.status_code not in (200, 204):
            err = patch_resp.text or f"PATCH agent {patch_resp.status_code}"
            logger.warning("Backend PATCH agent failed: %s", err)
            return {"error": err}
        logger.info(
            "Backend patch agent tool enabled: agent_id=%s tool_id=%s enabled=%s",
            agent_id,
            tool_id,
            enabled,
        )
        return {"success": True, "message": f"Tool {'enabled' if enabled else 'disabled'} on agent"}
    except requests.RequestException as e:
        logger.warning("Backend agent request failed: %s", e)
        return {"error": str(e)}
