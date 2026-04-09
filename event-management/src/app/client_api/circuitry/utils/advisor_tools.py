"""
Advisor-tool helpers for circuitry flows.

Pure functions to extract advisor_id from tool configs and to get
enabled business tool_ids from agent config.
"""

from typing import Any


def get_advisor_id_from_tool(tool: Any) -> str | None:
    """
    Extract advisor_id from a single business-tool dict.

    Checks api_config.body_template.advisor_id and
    pre_requests[0].body_template.advisor_id. Returns the first found.

    Args:
        tool: One tool object from Pipecat GET business-tools (e.g. from response["data"]).

    Returns:
        Advisor ID string if present, else None.
    """
    if not isinstance(tool, dict):
        return None
    api_bt = (tool.get("api_config") or {}).get("body_template") or {}
    advisor_id = api_bt.get("advisor_id")
    if advisor_id:
        return advisor_id
    pre = tool.get("pre_requests") or []
    if pre and isinstance(pre[0], dict):
        pre_bt = (pre[0].get("body_template") or {})
        advisor_id = pre_bt.get("advisor_id")
        if advisor_id:
            return advisor_id
    return None


def get_enabled_business_tool_ids(agent_config: Any) -> list[str]:
    """
    Extract enabled business tool_ids from agent config.

    Args:
        agent_config: The "config" object from backend GET agent response.

    Returns:
        List of tool_id strings for which enabled is True. Empty list if invalid.
    """
    if not isinstance(agent_config, dict):
        return []
    tools = agent_config.get("tools")
    if not isinstance(tools, dict):
        return []
    business_tools = tools.get("business_tools")
    if not isinstance(business_tools, list):
        return []
    result = []
    for entry in business_tools:
        if isinstance(entry, dict) and entry.get("enabled") is True:
            tid = entry.get("tool_id")
            if tid:
                result.append(str(tid))
    return result


def is_any_enabled_business_tool_in_set(agent_doc: Any, tool_ids: set[str]) -> bool:
    """
    True if agent_doc has at least one enabled business tool whose tool_id is in tool_ids.
    """
    if not tool_ids or not isinstance(agent_doc, dict):
        return False
    normalized = {str(t).strip() for t in tool_ids if str(t).strip()}
    if not normalized:
        return False
    for tid in get_enabled_business_tool_ids(agent_doc):
        if str(tid).strip() in normalized:
            return True
    return False


def is_business_tool_enabled_on_agent(agent_doc: Any, tool_id: str) -> bool:
    """
    True if agent_doc has tools.business_tools entry for tool_id with enabled True.

    agent_doc: Full agent document from backend list or GET (tools at top level).
    """
    if not tool_id or not isinstance(agent_doc, dict):
        return False
    want = str(tool_id).strip()
    if not want:
        return False
    for tid in get_enabled_business_tool_ids(agent_doc):
        if str(tid).strip() == want:
            return True
    return False


def get_all_business_tool_entries(agent_config: Any) -> list[dict[str, Any]]:
    """
    Extract all business_tool entries (tool_id + enabled) from agent config.

    Args:
        agent_config: The "config" object from backend GET agent response.

    Returns:
        List of dicts with "tool_id" and "enabled" keys. Empty list if invalid.
    """
    if not isinstance(agent_config, dict):
        return []
    tools = agent_config.get("tools")
    if not isinstance(tools, dict):
        return []
    business_tools = tools.get("business_tools")
    if not isinstance(business_tools, list):
        return []
    result = []
    for entry in business_tools:
        if isinstance(entry, dict):
            tid = entry.get("tool_id")
            if tid is not None:
                raw = entry.get("enabled")
                if raw is False:
                    enabled_val = False
                elif isinstance(raw, str) and raw.strip().lower() == "false":
                    enabled_val = False
                else:
                    enabled_val = raw is True or (
                        isinstance(raw, str) and raw.strip().lower() == "true"
                    )
                result.append({
                    "tool_id": str(tid),
                    "enabled": enabled_val,
                })
    return result
