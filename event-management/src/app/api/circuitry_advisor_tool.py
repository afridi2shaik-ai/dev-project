"""
Circuitry Advisor Tool API.

Client-facing endpoint to add a Circuitry advisor business tool to an agent,
to list advisor_ids for an agent's enabled business tools, and to list agents (id, name) that have any business tool enabled whose config references that advisor_id.
Validates input and requires id_token when auth is enabled.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.client_api.circuitry.backend_client import (
    get_agent,
    list_agents,
    patch_agent_add_tool,
    patch_agent_set_tool_enabled,
)
from app.client_api.circuitry.pipecat_client import (
    create_pipecat_business_tool,
    find_tool_by_advisor_id,
    get_or_create_circuitry_credential_id,
    get_pipecat_business_tool,
    get_pipecat_business_tools,
    resolve_all_business_tool_ids_for_advisor,
)
from app.client_api.circuitry.advisor_tool_template import build_advisor_tool_payload
from app.client_api.circuitry.utils import (
    get_all_business_tool_entries,
    get_advisor_id_from_tool,
    get_enabled_business_tool_ids,
    is_any_enabled_business_tool_in_set,
)
from app.models.circuitry_advisor import AdvisorToolRequest
from app.utils.auth_utils import validate_request_auth
from app.core.config import ADVANCE_LOGS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/advisor_tool")
async def add_advisor_tool_to_agent(request: Request, payload: AdvisorToolRequest):
    """
    Add or enable/disable a Circuitry advisor business tool on an agent.

    Body: agent_id, advisor_id, optional tenant_id, name, description, enabled (default true).
    When enabled=true: find or create the tool, then patch agent to add/enable it.
    When enabled=false: find the tool by advisor_id, then patch agent to set that tool disabled.
    """
    token_value = validate_request_auth(request, payload.tenant_id)

    logger.info(
        "Advisor tool request | agent_id=%s | advisor_id=%s | enabled=%s",
        payload.agent_id,
        payload.advisor_id,
        payload.enabled,
    )
    if ADVANCE_LOGS:
        logger.info("Advisor tool request payload: %s", payload.model_dump(mode="json"))

    if not payload.enabled:
        # Disable path: resolve tool by advisor_id from ALL business tools (enabled + disabled)
        agent_result = get_agent(payload.agent_id, token_value)
        if "error" in agent_result:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to get agent: {agent_result['error']}",
            )
        config = agent_result.get("config") if isinstance(agent_result.get("config"), dict) else (agent_result if isinstance(agent_result, dict) else None)
        all_entries = get_all_business_tool_entries(config) if config else []
        matching_tool_id = None
        already_disabled = False
        for entry in all_entries:
            tool_id = entry.get("tool_id")
            if not tool_id:
                continue
            full_tool = get_pipecat_business_tool(token_value, tool_id)
            if isinstance(full_tool, dict) and "error" not in full_tool:
                if str(get_advisor_id_from_tool(full_tool) or "").strip() == str(payload.advisor_id or "").strip():
                    matching_tool_id = tool_id
                    already_disabled = not entry.get("enabled", True)
                    break
        if matching_tool_id is None:
            logger.info(
                "Advisor tool POST reply | agent_id=%s | advisor_id=%s | message=Tool not attached to agent",
                payload.agent_id,
                payload.advisor_id,
            )
            return {
                "status": "ok",
                "message": "Tool not attached to agent",
                "agent_id": payload.agent_id,
                "advisor_id": payload.advisor_id,
                "tool_id": None,
                "enabled": False,
            }
        if already_disabled:
            logger.info(
                "Advisor tool POST reply | agent_id=%s | advisor_id=%s | message=Tool already disabled on agent | tool_id=%s",
                payload.agent_id,
                payload.advisor_id,
                matching_tool_id,
            )
            return {
                "status": "ok",
                "message": "Tool already disabled on agent",
                "agent_id": payload.agent_id,
                "advisor_id": payload.advisor_id,
                "tool_id": matching_tool_id,
                "enabled": False,
            }
        patch_result = patch_agent_set_tool_enabled(
            payload.agent_id, matching_tool_id, False, token_value
        )
        if ADVANCE_LOGS:
            logger.info("Patch agent set tool enabled (disable) result: %s", patch_result)
        if "error" in patch_result:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to disable tool on agent: {patch_result['error']}",
            )
        if ADVANCE_LOGS:
            logger.info("Advisor tool POST response (disable): agent_id=%s advisor_id=%s tool_id=%s patch_result=%s", payload.agent_id, payload.advisor_id, matching_tool_id, patch_result)
        logger.info(
            "Advisor tool POST reply | agent_id=%s | advisor_id=%s | message=Tool disabled on agent | tool_id=%s",
            payload.agent_id,
            payload.advisor_id,
            matching_tool_id,
        )
        return {
            "status": "ok",
            "message": "Tool disabled on agent",
            "agent_id": payload.agent_id,
            "advisor_id": payload.advisor_id,
            "tool_id": matching_tool_id,
            "enabled": False,
            "patch_result": patch_result,
        }

    # Enable path: reject if this advisor is already enabled on the agent (no duplicate advisor_id)
    agent_result = get_agent(payload.agent_id, token_value)
    if "error" in agent_result:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to get agent: {agent_result['error']}",
        )
    config = agent_result.get("config") if isinstance(agent_result.get("config"), dict) else (agent_result if isinstance(agent_result, dict) else None)
    enabled_tool_ids = get_enabled_business_tool_ids(config) if config else []
    current_advisor_ids = []
    for tid in enabled_tool_ids:
        full_tool = get_pipecat_business_tool(token_value, tid)
        if isinstance(full_tool, dict) and "error" not in full_tool:
            aid = get_advisor_id_from_tool(full_tool)
            if aid:
                current_advisor_ids.append(str(aid).strip())
    requested_advisor_normalized = str(payload.advisor_id or "").strip()
    if requested_advisor_normalized in current_advisor_ids:
        raise HTTPException(
            status_code=409,
            detail="Advisor already enabled on this agent. Duplicate advisor_id is not allowed.",
        )

    # Enable path: use list to find by advisor_id or create tool
    pipecat_reply = get_pipecat_business_tools(token_value)
    if ADVANCE_LOGS:
        logger.info("Pipecat business-tools list reply: %s", pipecat_reply)
    if pipecat_reply is None or (isinstance(pipecat_reply, dict) and "error" in pipecat_reply):
        err_msg = (pipecat_reply or {}).get("error", "unknown") if isinstance(pipecat_reply, dict) else "unknown"
        raise HTTPException(
            status_code=502,
            detail=f"Failed to get business tools from Pipecat: {err_msg}",
        )
    tools_list = pipecat_reply.get("data") or []
    matching_tool = find_tool_by_advisor_id(tools_list, payload.advisor_id)
    if ADVANCE_LOGS:
        logger.info(
            "Matching tool for advisor_id=%s: %s",
            payload.advisor_id,
            matching_tool if matching_tool is None else {"_id": matching_tool.get("_id"), "tool_id": matching_tool.get("tool_id"), "name": matching_tool.get("name")},
        )

    # Enable path: find or create tool, then add/enable on agent
    tool_id = None
    if matching_tool:
        tool_id = matching_tool.get("_id") or matching_tool.get("tool_id")
        if ADVANCE_LOGS:
            logger.info("Tool with advisor_id=%s found: tool_id=%s", payload.advisor_id, tool_id)
    else:
        # Resolve credential_id for this tenant (get or create via Pipecat)
        cred_result = get_or_create_circuitry_credential_id(token_value)
        if "error" in cred_result:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to get or create Circuitry credential: {cred_result['error']}",
            )
        credential_id = cred_result.get("credential_id")
        if not credential_id:
            raise HTTPException(status_code=502, detail="Credential resolution did not return credential_id")
        # Create tool via Pipecat business-tools API (use optional name/description from payload)
        tool_payload = build_advisor_tool_payload(
            payload.advisor_id,
            name=payload.name,
            description=payload.description,
            credential_id=credential_id,
        )
        create_result = create_pipecat_business_tool(token_value, tool_payload)
        if ADVANCE_LOGS:
            logger.info("Pipecat create business-tool result: %s", create_result)
        if "error" in create_result:
            err_msg = create_result["error"]
            # If tool with this name already exists, require client to pass unique name and description
            if "already exists" in err_msg.lower() and "tool with name" in err_msg.lower():
                tool_name = tool_payload.get("name") or "ask_circuitry_advisor"
                raise HTTPException(
                    status_code=409,
                    detail=f"Tool with name '{tool_name}' already exists. Pass a unique 'name' and 'description' in the request body for this advisor.",
                )
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to create business tool: {err_msg}",
                )
        else:
            tool_id = create_result.get("tool_id")
            if not tool_id:
                raise HTTPException(status_code=502, detail="Create tool did not return tool_id")
            if ADVANCE_LOGS:
                logger.info("Created business tool for advisor_id=%s: tool_id=%s", payload.advisor_id, tool_id)

    # Patch agent to add/enable this tool
    patch_result = patch_agent_add_tool(payload.agent_id, tool_id, token_value)
    if ADVANCE_LOGS:
        logger.info("Patch agent add tool result: %s", patch_result)
    if "error" in patch_result:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to add tool to agent: {patch_result['error']}",
        )

    response = {
        "status": "ok",
        "message": patch_result.get("message", "Tool added to agent"),
        "agent_id": payload.agent_id,
        "advisor_id": payload.advisor_id,
        "tool_id": tool_id,
        "tool_exists": matching_tool is not None,
        "enabled": True,
        "patch_result": patch_result,
    }
    if ADVANCE_LOGS:
        logger.info("Advisor tool POST response (enable): %s", response)
    logger.info(
        "Advisor tool POST reply | agent_id=%s | advisor_id=%s | message=%s | tool_id=%s",
        payload.agent_id,
        payload.advisor_id,
        response["message"],
        tool_id,
    )
    return response


@router.get("/agent_advisor_tools")
async def get_agent_advisor_tools(
    request: Request,
    agent_id: str = Query(..., description="Assistant/agent ID"),
):
    """
    Return advisor_ids for the agent's enabled business tools.

    GET agent from backend, list enabled business tool_ids, resolve to advisor_ids
    via Pipecat business-tools. Only tools that have an advisor_id in config are included.
    """
    token_value = validate_request_auth(request, None)

    logger.info("Agent advisor tools request | agent_id=%s", agent_id)

    agent_result = get_agent(agent_id, token_value)
    if "error" in agent_result:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to get agent: {agent_result['error']}",
        )

    # Backend may return config at top level (GET /api/agent) or under "config" key.
    config = agent_result.get("config") if isinstance(agent_result.get("config"), dict) else (agent_result if isinstance(agent_result, dict) else None)
    enabled_tool_ids = get_enabled_business_tool_ids(config) if config else []

    if not enabled_tool_ids:
        logger.info("Agent advisor tools reply | agent_id=%s | advisor_ids_count=0", agent_id)
        return {"agent_id": agent_id, "advisor_ids": []}

    advisor_ids = []
    for tool_id in enabled_tool_ids:
        full_tool = get_pipecat_business_tool(token_value, tool_id)
        if isinstance(full_tool, dict) and "error" not in full_tool:
            aid = get_advisor_id_from_tool(full_tool)
            if aid:
                advisor_ids.append(aid)

    # Return unique advisor_ids, preserving order
    seen = set()
    unique_advisor_ids = []
    for aid in advisor_ids:
        a = aid if isinstance(aid, str) else str(aid)
        if a not in seen:
            seen.add(a)
            unique_advisor_ids.append(aid)

    result = {"agent_id": agent_id, "advisor_ids": unique_advisor_ids}
    if ADVANCE_LOGS:
        logger.info("Agent advisor tools response: %s", result)
    logger.info(
        "Agent advisor tools reply | agent_id=%s | advisor_ids_count=%s",
        agent_id,
        len(unique_advisor_ids),
    )
    return result


@router.get("/advisor_agents")
async def get_agents_for_advisor(
    request: Request,
    advisor_id: str = Query(..., description="Circuitry advisor ID"),
):
    """
    Return agent id and name for each agent that has at least one enabled business tool
    whose Pipecat config references this advisor_id.

    Collects all Pipecat business tool_ids for the advisor (handles duplicate tool docs),
    then scans paginated backend agents. Skips disabled tool entries and agents not returned
    by the list API. Empty tool_ids and agents when no Pipecat tool references the advisor.
    """
    token_value = validate_request_auth(request, None)
    aid = (advisor_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="advisor_id is required")

    logger.info("Advisor agents request | advisor_id=%s", aid)

    tool_ids_set, perr = resolve_all_business_tool_ids_for_advisor(token_value, aid)
    if perr:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to resolve business tools for advisor: {perr.get('error', perr)}",
        )

    tool_ids_sorted = sorted(tool_ids_set)
    tool_id_primary = tool_ids_sorted[0] if tool_ids_sorted else None

    if not tool_ids_set:
        logger.info(
            "Advisor agents reply | advisor_id=%s | tool_ids_count=0 | agents_count=0",
            aid,
        )
        return {
            "advisor_id": aid,
            "tool_id": None,
            "tool_ids": [],
            "agents": [],
        }

    agents_out: list[dict[str, str]] = []
    skip = 0
    page_limit = 100
    while True:
        batch = list_agents(token_value, skip=skip, limit=page_limit)
        if "error" in batch:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to list agents: {batch['error']}",
            )
        for row in batch.get("data") or []:
            if not isinstance(row, dict):
                continue
            if not is_any_enabled_business_tool_in_set(row, tool_ids_set):
                continue
            ag_id = row.get("id") or row.get("_id")
            ag_id_str = str(ag_id) if ag_id is not None else ""
            name = row.get("name")
            name_str = name if isinstance(name, str) else (str(name) if name is not None else "")
            agents_out.append({"id": ag_id_str, "name": name_str})

        total = batch.get("total_items")
        n = len(batch.get("data") or [])
        if n < page_limit:
            break
        if total is not None and skip + n >= total:
            break
        skip += page_limit

    result = {
        "advisor_id": aid,
        "tool_id": tool_id_primary,
        "tool_ids": tool_ids_sorted,
        "agents": agents_out,
    }
    if ADVANCE_LOGS:
        logger.info("Advisor agents response: %s", result)
    logger.info(
        "Advisor agents reply | advisor_id=%s | tool_ids_count=%s | agents_count=%s",
        aid,
        len(tool_ids_set),
        len(agents_out),
    )
    return result
