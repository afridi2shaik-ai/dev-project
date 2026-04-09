"""Call Scheduler Tool

Allows the assistant to schedule automated callbacks when users request them.
"""

import datetime
from typing import Any

from loguru import logger
from pipecat.frames.frames import TTSSpeakFrame

try:  # pragma: no cover - optional import for type hints
    from pipecat.services.llm_service import FunctionCallParams  # type: ignore
except Exception:  # pragma: no cover
    FunctionCallParams = Any  # type: ignore

from app.services.callback_scheduler_client import (
    CallbackSchedulerClient,
    ScheduleCallbackRequest,
)
from app.utils.time_parse_utils import TimeParseError, format_scheduled_time


async def schedule_callback(
    params: "FunctionCallParams",
    scheduled_at_utc: str,
    engaging_words: str,
    reason: str,
    phone_number: str,
) -> None:
    """Schedule an automated callback at the specified UTC timestamp.

    This tool allows the assistant to schedule a callback when users request
    it. The timestamp should be in ISO format (e.g., "2025-12-15T14:30:00Z").

    Args:
        params: Tool invocation context provided by the LLM service.
        scheduled_at_utc: ISO timestamp string for when to call back (UTC timezone).
        engaging_words: Engaging/reassuring message to speak to the user about the callback.
        reason: Reason for the callback (why the user wants it).
        phone_number: Phone number to call back (required).
    """
    try:
        # Parse the timestamp
        try:
            scheduled_at = datetime.datetime.fromisoformat(scheduled_at_utc.replace('Z', '+00:00'))
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            logger.warning(f"Invalid timestamp format: {scheduled_at_utc}")
            await params.result_callback({
                "status": "error",
                "error": "time_parse_failed",
                "message": "Invalid time format provided",
                "scheduled_at_utc": scheduled_at_utc,
            })
            return

        # Get session context for full payload
        from app.tools.session_context_tool import get_session_context

        context = get_session_context()
        if not context:
            logger.error("No session context available for schedule_callback")
            await params.result_callback({
                "status": "error",
                "error": "no_session",
                "message": "Unable to schedule callback at this time",
            })
            return

        # Extract context information
        tenant_id = getattr(context.user, 'tenant_id', None)
        session_id = context.session_id
        assistant_id = getattr(context, 'assistant_id', None)

        if not tenant_id:
            logger.error("No tenant ID available for schedule_callback")
            await params.result_callback({
                "status": "error",
                "error": "no_tenant",
                "message": "Unable to schedule callback at this time",
            })
            return

        # Build user details
        user_details = {
            "name": getattr(context.user, 'name', None),
            "email": getattr(context.user, 'email', None),
            "user_id": getattr(context.user, 'user_id', None),
        }

        # Build transport info
        transport_info = {
            "mode": getattr(context.transport, 'mode', None),
            "user_phone_number": getattr(context.transport, 'user_phone_number', None),
            "agent_phone_number": getattr(context.transport, 'agent_phone_number', None),
            "call_direction": getattr(context.transport, 'call_direction', None),
        }

        # Create scheduler client
        scheduler_client = CallbackSchedulerClient()

        # Build the request payload
        request = ScheduleCallbackRequest(
            tenant_id=tenant_id,
            session_id=session_id,
            assistant_id=assistant_id or "unknown",
            requested_time_text=scheduled_at_utc,
            scheduled_at_utc=scheduled_at.isoformat(),
            reason=reason,
            phone_number=phone_number,
            user_details=user_details,
            transport_info=transport_info,
            session_metadata=getattr(context, 'metadata', None),
        )

        # Get the HTTP session from params (injected by wrapper)
        aiohttp_session = getattr(params, 'aiohttp_session', None)
        if not aiohttp_session:
            logger.error("No HTTP session available for schedule_callback")
            await params.result_callback({
                "status": "error",
                "error": "connection_error",
                "message": "Unable to schedule callback at this time",
            })
            return

        # Get access and ID tokens for authentication
        access_token = None
        id_token = None
        try:
            from app.services.token_provider import TokenProvider
            access_token, id_token = await TokenProvider.get_tokens_for_tenant(tenant_id)
            logger.debug("✅ Retrieved tokens for callback scheduler API")
        except Exception as token_error:
            logger.warning(f"⚠️ Could not retrieve tokens for callback scheduler: {token_error}. Proceeding without tokens.")
            # Continue without tokens - some APIs may not require authentication

        # Schedule the callback via API
        response = await scheduler_client.schedule_callback(
            request, 
            aiohttp_session,
            access_token=access_token,
            id_token=id_token
        )

        # Build result - only include essential response data, not input fields
        result = {
            "status": "success",
            "scheduled_at_formatted": format_scheduled_time(scheduled_at),
            "phone_number": phone_number,
            **response.raw_response,  # Include API response fields
        }

        await params.result_callback(result)

        # Speak engaging words AFTER successful scheduling
        if engaging_words:
            await params.llm.push_frame(TTSSpeakFrame(engaging_words))

    except TimeParseError as e:
        logger.warning(f"Time parsing failed: {e}")
        await params.result_callback({
            "status": "error",
            "error": "time_parse_failed",
            "message": "Could not understand the requested time",
            "scheduled_at_utc": scheduled_at_utc,
        })

    except Exception as e:
        logger.error(f"Callback scheduling failed: {e}", exc_info=True)
        await params.result_callback({
            "status": "error",
            "error": "scheduling_failed",
            "message": "Unable to schedule the callback right now. Please try again later.",
            "scheduled_at_utc": scheduled_at_utc,
        })
