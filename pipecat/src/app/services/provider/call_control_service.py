"""Call Control Service

Provides provider-agnostic interface for call control actions:
- Put caller on hold
- Initiate outbound call
- Merge calls into conference
"""

from typing import Any
from loguru import logger
from app.services.provider.plivo_transfer_service import (
    _plivo_initiate_outbound_call, _plivo_merge_calls, _plivo_put_on_hold, CallControlError)


async def put_caller_on_hold(provider: str, call_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Put the caller on hold.
    
    Args:
        provider: The telephony provider ('twilio' or 'plivo')
        call_id: The call identifier (call_sid for Twilio, call_uuid for Plivo)
    
    Returns:
        Dictionary with status and details of the hold action
    """
    try:
        if provider == "twilio":
            return await _twilio_put_on_hold(call_id)
        elif provider == "plivo":
            return await _plivo_put_on_hold(call_id, session_id=session_id)
        else:
            raise CallControlError(f"Provider '{provider}' does not support call hold")
    except Exception as e:
        logger.error(f"Error putting call on hold: {e}")
        raise CallControlError(f"Failed to put call on hold: {e!s}")


async def initiate_outbound_call_to_agent(
    provider: str,
    to_phone_number: str,
    from_phone_number: str | None = None,
    base_url: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Initiate an outbound call to Human Agent.
    """
    try:
        if provider == "twilio":
            return await _twilio_initiate_outbound_call(
                to_phone_number, from_phone_number, base_url, session_id, tenant_id
            )
        elif provider == "plivo":
            return await _plivo_initiate_outbound_call(
                to_phone_number, from_phone_number, base_url, session_id, tenant_id
            )
        else:
            raise CallControlError(f"Provider '{provider}' does not support outbound calls")
    except Exception as e:
        logger.error(f"Error initiating outbound call: {e}")
        raise CallControlError(f"Failed to initiate outbound call: {e!s}")


async def merge_calls(
    provider: str,
    original_call_id: str,
    new_call_id: str,
    conference_name: str | None = None,
    base_url: str | None = None,  # Add base_url parameter
) -> dict[str, Any]:
    """Merge two calls into a conference.
    
    Args:
        provider: The telephony provider ('twilio' or 'plivo')
        original_call_id: The original call identifier (Caller A)
        new_call_id: The new call identifier (Agent C)
        conference_name: Optional conference room name
        base_url: Base URL for callbacks (required for Plivo)
    
    Returns:
        Dictionary with status and conference details
    """
    try:
        if provider == "twilio":
            return await _twilio_merge_calls(original_call_id, new_call_id, conference_name)
        elif provider == "plivo":
            return await _plivo_merge_calls(original_call_id, new_call_id, conference_name, base_url)  # Pass base_url
        else:
            raise CallControlError(f"Provider '{provider}' does not support call merging")
    except Exception as e:
        logger.error(f"Error merging calls: {e}")
        raise CallControlError(f"Failed to merge calls: {e!s}")




