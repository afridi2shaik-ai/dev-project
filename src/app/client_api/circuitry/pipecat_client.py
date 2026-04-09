"""
Pipecat API client for event-management.

Calls Pipecat endpoints (e.g. business-tools) using the same base URL and token.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from app.client_api.circuitry.utils.advisor_tools import get_advisor_id_from_tool
from app.core.config import PIPECAT_BASE_URL, CIRCUITRY_CREDENTIAL_NAME, CIRCUITRY_EMAIL, CIRCUITRY_PASSWORD, CIRCUITRY_API_BASE_URL, ADVANCE_LOGS

logger = logging.getLogger(__name__)

PIPECAT_BUSINESS_TOOLS_PATH = "/vagent/api/business-tools"
PIPECAT_CREDENTIALS_PATH = "/vagent/api/credentials"


def _tool_dict_matches_advisor_id(tool: Any, advisor_id: str) -> bool:
    """True if tool dict embeds advisor_id in api_config or first pre_request body_template."""
    if not isinstance(tool, dict):
        return False
    want = (advisor_id or "").strip()
    if not want:
        return False
    api_bt = (tool.get("api_config") or {}).get("body_template") or {}
    if str(api_bt.get("advisor_id") or "").strip() == want:
        return True
    pre = tool.get("pre_requests") or []
    if pre and isinstance(pre[0], dict):
        pre_bt = (pre[0].get("body_template") or {})
        if str(pre_bt.get("advisor_id") or "").strip() == want:
            return True
    return False


def find_tool_by_advisor_id(tools_list: list[Any], advisor_id: str) -> dict[str, Any] | None:
    """
    Find a tool in the list that has the given advisor_id in its config.

    Checks api_config.body_template.advisor_id and pre_requests[0].body_template.advisor_id.
    Use with the "data" array from GET business-tools response (when items include full config).
    Note: If Pipecat list returns only summary items (no api_config), this returns None;
    use when full tool objects are available.

    Args:
        tools_list: List of tool dicts (e.g. response["data"] from list business-tools).
        advisor_id: Advisor ID to search for.

    Returns:
        The first matching tool dict (with _id / tool_id), or None if not found.
    """
    if not advisor_id or not tools_list:
        return None
    advisor_id = advisor_id.strip()
    for tool in tools_list:
        if _tool_dict_matches_advisor_id(tool, advisor_id):
            return tool
    return None


def find_tool_by_name(tools_list: list[Any], name: str) -> dict[str, Any] | None:
    """
    Find a tool in the list by its name (list returns name in summary).

    Use when Pipecat list only has summary fields and we cannot match by advisor_id;
    e.g. when create fails with "Tool with name 'X' already exists", find X and use its id.

    Args:
        tools_list: List of tool dicts (e.g. response["data"] from list business-tools).
        name: Tool name to search for.

    Returns:
        The first matching tool dict (with _id / tool_id), or None if not found.
    """
    if not name or not tools_list:
        return None
    name = name.strip()
    for tool in tools_list:
        if isinstance(tool, dict) and (tool.get("name") or "").strip() == name:
            return tool
    return None


def get_pipecat_business_tools(
    token_value: str | None,
    skip: int = 0,
    limit: int = 100,
    timeout: int = 15,
) -> dict | None:
    """
    Call Pipecat GET /vagent/api/business-tools (list business tools).

    Args:
        token_value: JWT for Authorization and x-id-token headers (optional).
        skip: Pagination skip.
        limit: Pagination limit.
        timeout: Request timeout in seconds.

    Returns:
        Response JSON dict, or None if PIPECAT_BASE_URL is not set.
        On request failure, returns a dict with key "error" and message.
    """
    if not PIPECAT_BASE_URL:
        logger.warning("PIPECAT_BASE_URL not set, skipping business-tools call")
        return None

    url = f"{PIPECAT_BASE_URL.rstrip('/')}{PIPECAT_BUSINESS_TOOLS_PATH}"
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["x-id-token"] = token_value

    try:
        resp = requests.get(
            url,
            params={"skip": skip, "limit": limit},
            headers=headers,
            timeout=timeout,
        )
        data = resp.json() if resp.content else None
        if ADVANCE_LOGS:
            logger.info("Pipecat business-tools reply (status=%s): %s", resp.status_code, data)
        else:
            total_items = data.get("total_items") if isinstance(data, dict) else None
            total_pages = data.get("total_pages") if isinstance(data, dict) else None
            logger.info("Pipecat business-tools reply (status=%s): total_items=%s total_pages=%s", resp.status_code, total_items, total_pages)
        if resp.status_code != 200:
            err = (data.get("detail") if isinstance(data, dict) else None) or resp.text or f"HTTP {resp.status_code}"
            return {"error": str(err)}
        return data
    except requests.RequestException as e:
        logger.warning("Pipecat business-tools request failed: %s", e)
        return {"error": str(e)}


def create_pipecat_business_tool(
    token_value: str | None,
    tool_payload: dict[str, Any],
    timeout: int = 15,
) -> dict[str, Any]:
    """
    Call Pipecat POST /vagent/api/business-tools to create a business tool.

    Args:
        token_value: JWT for Authorization and x-id-token headers (optional).
        tool_payload: Full business tool create payload (name, description, parameters,
            pre_requests, api_config, engaging_words). Must match Pipecat BusinessToolCreateRequest.
        timeout: Request timeout in seconds.

    Returns:
        Dict with "tool_id" key on success, or "error" key on failure.
        If PIPECAT_BASE_URL is not set, returns {"error": "PIPECAT_BASE_URL not set"}.
    """
    if not PIPECAT_BASE_URL:
        logger.warning("PIPECAT_BASE_URL not set, skipping create business-tool")
        return {"error": "PIPECAT_BASE_URL not set"}

    url = f"{PIPECAT_BASE_URL.rstrip('/')}{PIPECAT_BUSINESS_TOOLS_PATH}"
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["x-id-token"] = token_value

    try:
        resp = requests.post(url, json=tool_payload, headers=headers, timeout=timeout)
        # Pipecat create returns 201 with body = tool_id (plain string)
        if resp.status_code == 201:
            tool_id = resp.text.strip().strip('"')
            if not tool_id and resp.content:
                try:
                    tool_id = resp.json()
                except Exception:
                    tool_id = resp.text.strip()
            logger.info("Pipecat create business-tool success: tool_id=%s", tool_id)
            return {"tool_id": tool_id}
        body = resp.json() if resp.content else {}
        err = body.get("detail", resp.text) or f"HTTP {resp.status_code}"
        logger.warning("Pipecat create business-tool failed: %s", err)
        return {"error": str(err)}
    except requests.RequestException as e:
        logger.warning("Pipecat create business-tool request failed: %s", e)
        return {"error": str(e)}


def get_pipecat_business_tool(
    token_value: str | None,
    tool_id: str,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    Call Pipecat GET /vagent/api/business-tools/{tool_id} to get full tool config.

    Returns the full BusinessTool (including api_config, pre_requests) so we can
    extract advisor_id and other fields that are not in the list response.

    Args:
        token_value: JWT for Authorization and x-id-token headers (optional).
        tool_id: Business tool ID.
        timeout: Request timeout in seconds.

    Returns:
        Full tool dict on success, or dict with "error" key on failure.
    """
    if not PIPECAT_BASE_URL:
        return {"error": "PIPECAT_BASE_URL not set"}
    if not (tool_id or str(tool_id).strip()):
        return {"error": "tool_id is required"}

    url = f"{PIPECAT_BASE_URL.rstrip('/')}{PIPECAT_BUSINESS_TOOLS_PATH}/{tool_id.strip()}"
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["x-id-token"] = token_value

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            return data
        err = resp.text or f"HTTP {resp.status_code}"
        if resp.content:
            try:
                data = resp.json()
                err = data.get("detail", err)
            except Exception:
                pass
        logger.warning("Pipecat get business-tool failed: %s", err)
        return {"error": str(err)}
    except requests.RequestException as e:
        logger.warning("Pipecat get business-tool request failed: %s", e)
        return {"error": str(e)}


def _business_tools_page_may_be_summary(tools_list: list[Any]) -> bool:
    for t in tools_list:
        if isinstance(t, dict) and (t.get("_id") or t.get("tool_id")):
            if not t.get("api_config") and not t.get("pre_requests"):
                return True
    return False


def _parallel_resolve_tool_id_from_summary_tools(
    token_value: str | None,
    tools_list: list[Any],
    want_advisor_id: str,
    timeout: int,
    max_workers: int = 12,
) -> str | None:
    """
    Pipecat list returned summaries only; fetch full tool configs in parallel
    until one matches want_advisor_id.
    """
    seen: set[str] = set()
    tool_ids: list[str] = []
    for tool in tools_list:
        if not isinstance(tool, dict):
            continue
        raw_id = tool.get("_id") or tool.get("tool_id")
        if not raw_id:
            continue
        tid_str = str(raw_id).strip()
        if not tid_str or tid_str in seen:
            continue
        seen.add(tid_str)
        tool_ids.append(tid_str)

    if not tool_ids:
        return None

    workers = min(max_workers, len(tool_ids))

    def check_one(tid_str: str) -> str | None:
        full = get_pipecat_business_tool(token_value, tid_str, timeout=timeout)
        if not isinstance(full, dict) or "error" in full:
            return None
        aid = get_advisor_id_from_tool(full)
        if aid and str(aid).strip() == want_advisor_id:
            return tid_str
        return None

    executor = ThreadPoolExecutor(max_workers=workers)
    matched_result: str | None = None
    try:
        futures = [executor.submit(check_one, tid) for tid in tool_ids]
        for fut in as_completed(futures):
            try:
                m = fut.result()
                if m:
                    matched_result = m
                    break
            except Exception:
                logger.warning("Parallel Pipecat get business-tool failed", exc_info=True)
    finally:
        executor.shutdown(
            wait=(matched_result is None),
            cancel_futures=(matched_result is not None),
        )
    return matched_result


def _parallel_collect_tool_ids_from_summary_tools(
    token_value: str | None,
    tools_list: list[Any],
    want_advisor_id: str,
    timeout: int,
    max_workers: int = 12,
) -> set[str]:
    """
    Pipecat list returned summaries; fetch full tool configs in parallel and collect
    every tool_id whose config matches want_advisor_id (all matches, deterministic completion).
    """
    seen: set[str] = set()
    tool_ids: list[str] = []
    for tool in tools_list:
        if not isinstance(tool, dict):
            continue
        raw_id = tool.get("_id") or tool.get("tool_id")
        if not raw_id:
            continue
        tid_str = str(raw_id).strip()
        if not tid_str or tid_str in seen:
            continue
        seen.add(tid_str)
        tool_ids.append(tid_str)

    if not tool_ids:
        return set()

    workers = min(max_workers, len(tool_ids))
    want = want_advisor_id.strip()

    def check_one(tid_str: str) -> str | None:
        full = get_pipecat_business_tool(token_value, tid_str, timeout=timeout)
        if not isinstance(full, dict) or "error" in full:
            return None
        aid = get_advisor_id_from_tool(full)
        if aid and str(aid).strip() == want:
            return tid_str
        return None

    out: set[str] = set()
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(check_one, tid) for tid in tool_ids]
        for fut in as_completed(futures):
            try:
                m = fut.result()
                if m:
                    out.add(m)
            except Exception:
                logger.warning("Parallel Pipecat get business-tool failed", exc_info=True)
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
    return out


def resolve_all_business_tool_ids_for_advisor(
    token_value: str | None,
    advisor_id: str,
    page_limit: int = 100,
    timeout: int = 15,
) -> tuple[set[str], dict[str, Any] | None]:
    """
    Paginate all Pipecat business-tools and collect every tool_id whose config references advisor_id.

    Returns:
        (set of tool_id strings, None) on success (possibly empty if no tool matches),
        (empty set, error_dict) on Pipecat list failure.
    """
    if not (advisor_id or "").strip():
        return set(), None
    want = advisor_id.strip()
    matched: set[str] = set()
    skip = 0
    while True:
        reply = get_pipecat_business_tools(token_value, skip=skip, limit=page_limit, timeout=timeout)
        if reply is None:
            return set(), {"error": "PIPECAT_BASE_URL not set"}
        if isinstance(reply, dict) and "error" in reply:
            return set(), reply

        tools_list = reply.get("data") or []

        if tools_list and _business_tools_page_may_be_summary(tools_list):
            matched.update(
                _parallel_collect_tool_ids_from_summary_tools(
                    token_value, tools_list, want, timeout=timeout
                )
            )
        else:
            for tool in tools_list:
                if _tool_dict_matches_advisor_id(tool, want):
                    tid = tool.get("_id") or tool.get("tool_id")
                    if tid:
                        matched.add(str(tid).strip())

        total_items = reply.get("total_items")
        n = len(tools_list)
        if n < page_limit:
            break
        if total_items is not None and skip + n >= total_items:
            break
        skip += page_limit

    return matched, None


def resolve_business_tool_id_for_advisor(
    token_value: str | None,
    advisor_id: str,
    page_limit: int = 100,
    timeout: int = 15,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    Paginate Pipecat business-tools until a tool with this advisor_id is found.

    Uses list response when it includes advisor_id in config; if the page looks like
    a summary (no api_config/pre_requests), fetches each tool by id on that page in parallel.

    Returns:
        (tool_id, None) on success,
        (None, error_dict) on Pipecat failure,
        (None, None) if not found across all pages.
    """
    if not (advisor_id or "").strip():
        return None, None
    want = advisor_id.strip()

    skip = 0
    while True:
        reply = get_pipecat_business_tools(token_value, skip=skip, limit=page_limit, timeout=timeout)
        if reply is None:
            return None, {"error": "PIPECAT_BASE_URL not set"}
        if isinstance(reply, dict) and "error" in reply:
            return None, reply

        tools_list = reply.get("data") or []
        match = find_tool_by_advisor_id(tools_list, want)
        if match:
            tid = match.get("_id") or match.get("tool_id")
            return (str(tid) if tid else None), None

        if tools_list and _business_tools_page_may_be_summary(tools_list):
            matched_id = _parallel_resolve_tool_id_from_summary_tools(
                token_value, tools_list, want, timeout=timeout
            )
            if matched_id:
                return matched_id, None

        total_items = reply.get("total_items")
        n = len(tools_list)
        if n < page_limit:
            break
        if total_items is not None and skip + n >= total_items:
            break
        skip += page_limit

    return None, None


def get_pipecat_credentials(
    token_value: str | None,
    page: int = 1,
    limit: int = 100,
    timeout: int = 15,
) -> dict | None:
    """
    Call Pipecat GET /vagent/api/credentials (list API credentials).

    Args:
        token_value: JWT for Authorization and x-id-token headers (optional).
        page: Page number (1-based).
        limit: Items per page.
        timeout: Request timeout in seconds.

    Returns:
        Response JSON dict (with "data" list of credentials), or None if PIPECAT_BASE_URL not set.
        On failure, returns a dict with key "error".
    """
    if not PIPECAT_BASE_URL:
        logger.warning("PIPECAT_BASE_URL not set, skipping credentials list")
        return None

    url = f"{PIPECAT_BASE_URL.rstrip('/')}{PIPECAT_CREDENTIALS_PATH}"
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["x-id-token"] = token_value

    try:
        resp = requests.get(
            url,
            params={"page": page, "limit": limit},
            headers=headers,
            timeout=timeout,
        )
        data = None
        if resp.content:
            try:
                data = resp.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                pass
        if resp.status_code != 200:
            err = (data.get("detail") if isinstance(data, dict) else None) or resp.text or f"HTTP {resp.status_code}"
            logger.warning("Pipecat credentials list failed: %s", err)
            return {"error": str(err)}
        if data is None:
            logger.warning(
                "Pipecat credentials list returned empty or invalid JSON (status=%s, body=%s)",
                resp.status_code,
                (resp.text or "")[:300],
            )
            return {"error": f"Credentials list returned empty or invalid response (status={resp.status_code})"}
        return data
    except requests.RequestException as e:
        logger.warning("Pipecat credentials list request failed: %s", e)
        return {"error": str(e)}


def create_pipecat_credential(
    token_value: str | None,
    credential_payload: dict[str, Any],
    timeout: int = 15,
) -> dict[str, Any]:
    """
    Call Pipecat POST /vagent/api/credentials to create an API credential.

    Args:
        token_value: JWT for Authorization and x-id-token headers (optional).
        credential_payload: Body matching Pipecat APICredentialCreateRequest.
        timeout: Request timeout in seconds.

    Returns:
        Dict with "credential_id" on success, or "error" on failure.
    """
    if not PIPECAT_BASE_URL:
        return {"error": "PIPECAT_BASE_URL not set"}

    url = f"{PIPECAT_BASE_URL.rstrip('/')}{PIPECAT_CREDENTIALS_PATH}"
    headers = {"Content-Type": "application/json"}
    if token_value:
        headers["Authorization"] = f"Bearer {token_value}"
        headers["x-id-token"] = token_value

    try:
        resp = requests.post(url, json=credential_payload, headers=headers, timeout=timeout)
        if resp.status_code == 201:
            credential_id = resp.text.strip().strip('"')
            if not credential_id and resp.content:
                try:
                    credential_id = resp.json()
                except Exception:
                    credential_id = resp.text.strip()
            logger.info("Pipecat create credential success: credential_id=%s", credential_id)
            return {"credential_id": credential_id}
        body = resp.json() if resp.content else {}
        err = body.get("detail", resp.text) or f"HTTP {resp.status_code}"
        logger.warning("Pipecat create credential failed: %s", err)
        return {"error": str(err)}
    except requests.RequestException as e:
        logger.warning("Pipecat create credential request failed: %s", e)
        return {"error": str(e)}


def _build_circuitry_credential_payload(credential_name: str) -> dict[str, Any]:
    """Build the create-credential payload for Circuitry AI (token endpoint + body from config)."""
    token_endpoint = f"{CIRCUITRY_API_BASE_URL.rstrip('/')}/v3/data/token"
    return {
        "credential_name": credential_name,
        "description": "Circuitry AI authentication credentials for advisor tools",
        "api_provider": credential_name,
        "token_request": {
            "endpoint": token_endpoint,
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body_template": {
                "email": CIRCUITRY_EMAIL or "",
                "password": CIRCUITRY_PASSWORD or "",
            },
        },
        "token_response": {
            "tokens": [
                {
                    "name": "access_token",
                    "response_path": "data.token",
                    "header_name": "Authorization",
                    "header_format": "Bearer {token}",
                }
            ]
        },
    }


def get_or_create_circuitry_credential_id(token_value: str | None) -> dict[str, Any]:
    """
    Get or create the Circuitry credential in Pipecat for the current tenant (from token).
    Uses CIRCUITRY_CREDENTIAL_NAME from config (env) to find or create.

    Returns:
        Dict with "credential_id" on success, or "error" on failure.
    """
    credential_name = CIRCUITRY_CREDENTIAL_NAME or "circuitry_ai_dev"
    list_resp = get_pipecat_credentials(token_value, page=1, limit=200)
    if list_resp is None:
        return {"error": "PIPECAT_BASE_URL not set"}
    if "error" in list_resp:
        return list_resp

    data = list_resp.get("data") or []
    for item in data:
        if isinstance(item, dict) and item.get("credential_name") == credential_name:
            cred_id = item.get("id") or item.get("_id")
            if cred_id:
                logger.info("Found existing Circuitry credential: %s", cred_id)
                return {"credential_id": str(cred_id)}

    if not CIRCUITRY_EMAIL or not CIRCUITRY_PASSWORD:
        return {"error": "CIRCUITRY_CREDENTIALS (email,password) not set; cannot create credential"}

    payload = _build_circuitry_credential_payload(credential_name)
    create_resp = create_pipecat_credential(token_value, payload)
    return create_resp
