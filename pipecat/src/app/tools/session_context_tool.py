"""Session Context Tool

This tool allows the AI to query information about the current session:
- How the user is connecting (web, phone, etc.)
- User details (name, phone number, email)
- Session metadata
- Transport-specific information

The AI can use this to provide contextual responses like:
"I see you're calling from +1-555-123-4567"
"Hi John, I see you're using our web interface"
"""

from typing import Any

from loguru import logger
from pipecat.services.llm_service import FunctionCallParams

from app.schemas import SessionContext

# Global context storage for the current session
_current_session_context: SessionContext | None = None


def set_session_context(context: SessionContext) -> None:
    """Set the current session context for use by the AI."""
    global _current_session_context
    _current_session_context = context
    logger.info(f"Session context set for {context.session_id}: {context.transport.mode} - {context.user.name or 'anonymous'}")


def get_session_context() -> SessionContext | None:
    """Get the current session context."""
    return _current_session_context


async def get_session_info(params: FunctionCallParams, include_sensitive: bool = False) -> dict[str, Any]:
    """Get information about the current session and user context.

    This function allows the AI to understand:
    - How the user is connecting (web interface, phone call, etc.)
    - User identification details
    - Session timing and metadata
    - Transport-specific information

    Args:
        include_sensitive: Whether to include sensitive info like full phone numbers

    Returns:
        Dictionary containing session context information
    """
    try:
        context = get_session_context()
        if not context:
            logger.warning("No session context available for AI query")
            result = {"status": "error", "message": "No session context available", "context": None}
            await params.result_callback(result)
            return result

        # Build response with appropriate level of detail
        session_info = {"transport_mode": context.transport.mode.value, "session_id": context.session_id, "session_started": context.session_start_time.isoformat(), "user_reference": context.get_reference_context(), "greeting_context": context.get_greeting_context()}

        # Add user details
        user_info = {}
        if context.user.name:
            user_info["name"] = context.user.name
        if context.user.email and include_sensitive:
            user_info["email"] = context.user.email
        if context.user.user_id and include_sensitive:
            user_info["user_id"] = context.user.user_id

        if user_info:
            session_info["user"] = user_info

        # Add transport-specific details
        transport_info = {"mode": context.transport.mode.value}

        if context.transport.mode.value in ["twilio", "plivo"]:
            # Phone call context with clear who-called-whom information
            transport_info["type"] = "phone_call"
            if context.transport.call_sid:
                transport_info["call_id"] = context.transport.call_sid

            # Call direction and initiation context
            if context.transport.call_direction:
                transport_info["call_direction"] = context.transport.call_direction
            if context.transport.call_initiated_by:
                transport_info["initiated_by"] = context.transport.call_initiated_by

            # User's phone number (with privacy options)
            if context.transport.user_phone_number:
                if include_sensitive:
                    transport_info["user_phone_number"] = context.transport.user_phone_number
                else:
                    # Mask user phone number for privacy
                    number = context.transport.user_phone_number
                    if len(number) > 4:
                        transport_info["user_phone_number"] = f"***-***-{number[-4:]}"
                    else:
                        transport_info["user_phone_number"] = "***"

            # Agent/system phone number (usually OK to show)
            if context.transport.agent_phone_number:
                transport_info["agent_phone_number"] = context.transport.agent_phone_number

            # Raw from/to numbers for debugging (with privacy)
            if include_sensitive:
                if context.transport.from_number:
                    transport_info["raw_from_number"] = context.transport.from_number
                if context.transport.to_number:
                    transport_info["raw_to_number"] = context.transport.to_number

        elif context.transport.mode.value == "webrtc":
            # Web interface context
            transport_info["type"] = "web_interface"
            if context.transport.browser_info:
                transport_info["browser_available"] = True

        session_info["transport"] = transport_info

        # Add conversation metadata (non-sensitive)
        if context.conversation_metadata:
            metadata = {}
            for key, value in context.conversation_metadata.items():
                if key not in ["call_metadata", "transport_metadata"]:  # Skip potentially sensitive data
                    metadata[key] = value
            if metadata:
                session_info["metadata"] = metadata

        # Generate contextual suggestions for the AI
        suggestions = []

        if context.transport.mode.value in ["twilio", "plivo"]:
            if context.transport.call_direction == "inbound":
                suggestions.append("You can reference that the user called you")
                if context.transport.user_phone_number:
                    suggestions.append("You can mention they're calling from their phone")
                if context.transport.agent_phone_number:
                    suggestions.append(f"You can reference your phone number: {context.transport.agent_phone_number}")
            elif context.transport.call_direction == "outbound":
                suggestions.append("You can reference that you called the user")
                if context.transport.user_phone_number:
                    suggestions.append("You can mention you called them at their number")
                if context.transport.agent_phone_number:
                    suggestions.append(f"You can reference calling from: {context.transport.agent_phone_number}")
            else:
                suggestions.append("You can reference that this is a phone call")

        elif context.transport.mode.value == "webrtc":
            suggestions.append("You can reference that the user is using the web interface")

        if context.user.name:
            suggestions.append(f"You can address the user by name: {context.user.name}")

        session_info["ai_suggestions"] = suggestions

        result = {"status": "success", "session_info": session_info, "natural_reference": context.get_reference_context(), "contextual_greeting": context.get_greeting_context()}

        logger.info(f"Provided session context to AI for {context.session_id}")
        await params.result_callback(result)
        return result

    except Exception as e:
        logger.error(f"Error getting session info for AI: {e}")
        result = {"status": "error", "message": f"Error retrieving session information: {e!s}", "context": None}
        await params.result_callback(result)
        return result


# Function metadata for LLM registration
get_session_info.description = """Get information about the current session and user context.

Use this function to understand:
- How the user is communicating with you (web interface, phone call, etc.)
- User identification details (name, reference info)
- Session context and timing
- Transport-specific information

This helps you provide more personalized and contextual responses.
For example:
- "I see you're calling from your phone"
- "Hi John, thanks for using our web interface"
- "I notice this is a phone call, I can hear you clearly"

The information returned is privacy-aware and respects user data protection."""

get_session_info.parameters = {"type": "object", "properties": {"include_sensitive": {"type": "boolean", "description": "Whether to include sensitive information like full phone numbers and email addresses. Default is false for privacy.", "default": False}}, "required": []}

