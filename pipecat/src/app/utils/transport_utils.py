import asyncio
from typing import Any

import plivo
from loguru import logger
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.schemas.log_schema import Artifact, ArtifactType


def _get_plivo_call_details_sync(call_uuid: str, auth_id: str, auth_token: str) -> dict[str, Any]:
    """Synchronously fetch Plivo call details using provided credentials."""
    try:
        client = plivo.RestClient(auth_id, auth_token)
        response = client.calls.get(call_uuid)
        # The plivo SDK returns an object that can be cast to a dict
        return response.__dict__
    except Exception as e:
        logger.error(f"Error fetching Plivo call details for {call_uuid}: {e}")
        return {"error": str(e)}


def _get_twilio_call_details_sync(call_sid: str, account_sid: str, auth_token: str) -> dict[str, Any]:
    """Synchronously fetch Twilio call details using provided credentials."""
    try:
        client = Client(account_sid, auth_token)
        call_instance = client.calls(call_sid).fetch()
        # Manually construct a serializable dictionary.
        # The 'from' field is a reserved keyword, so the Twilio SDK uses '_from'.
        return {
            "sid": call_instance.sid,
            "to": call_instance.to,
            "from": call_instance._from,
            "status": call_instance.status,
            "start_time": call_instance.start_time,
            "end_time": call_instance.end_time,
            "duration": call_instance.duration,
            "price": call_instance.price,
            "price_unit": call_instance.price_unit,
            "direction": call_instance.direction,
            "answered_by": call_instance.answered_by,
        }
    except TwilioRestException as e:
        logger.error(f"Error fetching Twilio call details for {call_sid}: {e}")
        return {"error": str(e), "status": e.status}
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching Twilio call details for {call_sid}: {e}")
        return {"error": str(e)}


async def get_transport_details_artifact(
    transport_name: str,
    session_id: str,
    provider_session_id: str,
    api_key: str | None = None,
    auth_token: str | None = None,
) -> Artifact | None:
    """Fetch transport details using provided credentials.
    
    Args:
        transport_name: Transport provider name ("plivo" or "twilio")
        session_id: Session identifier
        provider_session_id: Provider-specific session ID (call_uuid for Plivo, call_sid for Twilio)
        api_key: API key/account identifier (auth_id for Plivo, account_sid for Twilio)
        auth_token: Authentication token for the provider
    
    This function does not access the database. All database operations
    should be handled by the caller (e.g., ArtifactManager) using managers.
    """
    details = {}

    # Add a delay to allow telephony providers to finalize the call record.
    await asyncio.sleep(2)

    if transport_name == "plivo":
        if not api_key or not auth_token:
            logger.warning(f"Missing Plivo credentials for session {session_id}")
            return None
        logger.info(f"Fetching Plivo call details for {provider_session_id}")
        details = await asyncio.to_thread(
            _get_plivo_call_details_sync, provider_session_id, api_key, auth_token
        )
    elif transport_name == "twilio":
        if not api_key or not auth_token:
            logger.warning(f"Missing Twilio credentials for session {session_id}")
            return None
        logger.info(f"Fetching Twilio call details for {provider_session_id}")
        details = await asyncio.to_thread(
            _get_twilio_call_details_sync, provider_session_id, api_key, auth_token
        )
    else:
        # Not a telephony transport we can get details for
        return None

    if details:
        logger.info(f"Saved transport details for session {session_id}")
        return Artifact(artifact_type=ArtifactType.TRANSPORT_DETAILS, content=details)
    return None