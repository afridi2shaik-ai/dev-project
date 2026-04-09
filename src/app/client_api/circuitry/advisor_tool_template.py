"""
Circuitry advisor tool template for create payload.

Replace advisor_id in the template via build_advisor_tool_payload(advisor_id).
Edit ADVISOR_TOOL_TEMPLATE when you have the final structure.
"""

import copy
from typing import Any

from app.core.config import URL_CIRCUITRY_BUSINESS_TOOL


# Default structure; set advisor_id in both pre_requests[0].body_template and api_config.body_template
ADVISOR_TOOL_TEMPLATE: dict[str, Any] = {
    "name": "ask_circuitry_advisor",
    "description": "Ask a question to Circuitry AI advisor about equipment maintenance and manuals. The system will initialize a conversation session and then submit your question.",
    "parameters": [
        {
            "name": "user_question",
            "type": "string",
            "description": "The user's question about equipment, manuals, or maintenance procedures",
            "required": True,
            "examples": [
                "How do I fill the liquid reservoir for the DS-40i?",
                "What is the maintenance schedule for the printer?",
            ],
        }
    ],
    "pre_requests": [
        {
            "name": "initialize_session",
            "description": "Initialize conversation session with Circuitry AI to get sender_id",
            "endpoint": "/api/v1/start-stream",
            "method": "POST",
            "body_template": {
                "advisor_id": "__ADVISOR_ID__",
                "token": "{{auth_token}}",
            },
            "extract_fields": {"sender_id": "sender_id"},
            "timeout_seconds": 10,
            "cache_config": {"enabled": True, "cache_key": "circuitry_ai_session"},
        }
    ],
    "api_config": {
        "base_url": "https://dev.dialogue.circuitry.ai",
        "endpoint": "/api/v1/chat",
        "method": "POST",
        "timeout_seconds": 30,
        "authentication": {
            "type": "custom_token_db",
            "credential_id": "e89e478b-b7a4-4fc0-b421-7275473d7d1d",
        },
        "query_params": {},
        "body_template": {
            "advisor_id": "__ADVISOR_ID__",
            "user_message": "{{user_question}}",
            "sender_id": "{{pre_request.sender_id}}",
            "start_stream": False,
            "token": "{{auth_token}}",
            "metadata": {"imagesourceId": "", "imagetype": "", "jwt": "", "mentions": {}},
        },
        "success_message": "Here's what I found: {{response}}",
        "error_message": "I couldn't retrieve the information from the knowledge base right now. Please try again.",
    },
    "engaging_words": "Searching the manuals. Please stay online...",
}


def build_advisor_tool_payload(
    advisor_id: str,
    name: str | None = None,
    description: str | None = None,
    credential_id: str | None = None,
) -> dict[str, Any]:
    """
    Build the business tool create payload with advisor_id set in both places.

    Args:
        advisor_id: Circuitry advisor ID to use in pre_requests and api_config body_template.
        name: Optional tool name; if provided, overrides template default (used only when creating).
        description: Optional tool description; if provided, overrides template default (used only when creating).
        credential_id: Pipecat API credential id for custom_token_db auth; if provided, set in api_config.authentication.

    Returns:
        Deep copy of ADVISOR_TOOL_TEMPLATE with advisor_id set and optional name/description/credential_id.
    """
    payload = copy.deepcopy(ADVISOR_TOOL_TEMPLATE)
    advisor_id = (advisor_id or "").strip()
    if payload.get("api_config") and isinstance(payload["api_config"], dict):
        payload["api_config"]["base_url"] = URL_CIRCUITRY_BUSINESS_TOOL
    if name is not None and (name := str(name).strip()):
        payload["name"] = name
    if description is not None and (description := str(description).strip()):
        payload["description"] = description
    if credential_id is not None and (credential_id := str(credential_id).strip()):
        if payload.get("api_config") and isinstance(payload["api_config"], dict):
            auth = payload["api_config"].get("authentication") or {}
            if isinstance(auth, dict):
                auth = {**auth, "credential_id": credential_id}
                payload["api_config"]["authentication"] = auth
    if payload.get("pre_requests") and isinstance(payload["pre_requests"][0], dict):
        bt = payload["pre_requests"][0].get("body_template") or {}
        bt["advisor_id"] = advisor_id
        payload["pre_requests"][0]["body_template"] = bt
    if payload.get("api_config") and isinstance(payload["api_config"], dict):
        bt = (payload["api_config"].get("body_template") or {}).copy()
        bt["advisor_id"] = advisor_id
        payload["api_config"]["body_template"] = bt
    return payload
