from typing import Any

import plivo
from loguru import logger
from app.core.transports.plivo_websocket_manager import plivo_websocket_manager
from app.core import settings

class CallControlError(Exception):
    """Exception raised for call control errors."""
    pass

# Plivo implementations
async def _plivo_put_on_hold(call_uuid: str, session_id: str | None = None) -> dict[str, Any]:
    """Put the original caller on hold with looping music."""
    if not settings.PLIVO_AUTH_ID or not settings.PLIVO_AUTH_TOKEN:
        raise CallControlError("Plivo credentials not configured")
    
    client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
    
    try:
        # Play hold music on the original call using Plivo's Play API
        # This keeps the call active while playing music
        hold_music_url = "https://s3.amazonaws.com/plivocloud/music.mp3"
        logger.info(f"Playing hold music on Plivo call {call_uuid}")
        play_response = client.calls.play(
            call_uuid=call_uuid,
            urls=[hold_music_url],
            loop=True 
        )

        # if session_id:
        #     try:
        #         original_websocket = plivo_websocket_manager.get_connection(session_id)
        #         if original_websocket:
        #             await plivo_websocket_manager.cancel_pipeline_task(session_id)
        #             await original_websocket.close()
        #             plivo_websocket_manager.remove_connection(session_id)
        #             logger.info(f"🧹 Pipeline stopped & WebSocket closed for session {session_id} after hold started")
        #     except Exception as ws_err:
        #         logger.warning(f"⚠️ Could not stop WebSocket pipeline early: {ws_err}")

        if session_id:
            try:
                original_websocket = plivo_websocket_manager.get_connection(session_id)
                if original_websocket:
                    # DO NOT cancel the pipeline task - it will hang up the call
                    # Instead, just mark that warm transfer is active
                    # The pipeline will check this flag and skip hangup
                    # The WebSocket must stay open to keep the call active with hold music
                    logger.info(f"🧹 Warm transfer active - keeping pipeline and WebSocket open for session {session_id}")
                    # DO NOT call: await plivo_websocket_manager.cancel_pipeline_task(session_id)
                    # DO NOT close the WebSocket here - it will terminate the call
                    # The WebSocket will be closed when transferring to conference in plivo_conference_join
            except Exception as ws_err:
                logger.warning(f"⚠️ Could not access WebSocket: {ws_err}")

        response_dict = {
            "api_id": getattr(play_response, 'api_id', None),
            "message": getattr(play_response, 'message', None)
        }
        
        logger.info(f"Plivo call {call_uuid} put on hold with music: {play_response}")
        
        return {
            "status": "success",
            "action": "put_caller_on_hold",
            "call_id": call_uuid,
            "provider": "plivo",
            "play_response": response_dict,  
            "note": "Hold music playing (looped), call kept active for warm transfer",
        }
    except Exception as e:
        logger.error(f"Plivo API error putting call on hold: {e}")
        raise CallControlError(f"Plivo API error: {e!s}")


async def _plivo_initiate_outbound_call(
    to_phone_number: str,
    from_phone_number: str | None,
    base_url: str | None,
    session_id: str | None,
    tenant_id: str | None,
) -> dict[str, Any]:
    """Initiate Plivo outbound call  to supervisor (agent)."""
    if not settings.PLIVO_AUTH_ID or not settings.PLIVO_AUTH_TOKEN:
        raise CallControlError("Plivo credentials not configured")
    
    client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
    from_number = from_phone_number or settings.PLIVO_PHONE_NUMBER
    
    if not from_number:
        raise CallControlError("Plivo from number not configured")
    
    if not base_url:
        base_url = settings.BASE_URL
    
    # Strip trailing slash to avoid double slashes in URLs
    base_url = base_url.rstrip('/')
    
    answer_url = f"{base_url}/vagent/api/plivo/conference-join?session_id={session_id}&tenant_id={tenant_id}"
    hangup_url = f"{base_url}/vagent/api/plivo/hangup?session_id={session_id}&tenant_id={tenant_id}"

    try:
        call_params = {
            "from_": from_number,
            "to_": to_phone_number,
            "answer_url": answer_url,
            "answer_method": "POST",
            "hangup_url": hangup_url,
            "hangup_method": "POST",
        }
        
        response = client.calls.create(**call_params)
        
        call_uuid = response.request_uuid
        logger.info(f"Plivo outbound call initiated: {call_uuid} to {to_phone_number} with answer_url: {answer_url}")
        return {
            "status": "success",
            "action": "initiate_outbound_call_to_agent_C",
            "call_id": call_uuid,
            "to": to_phone_number,
            "from": from_number,
            "provider": "plivo",
        }
    except Exception as e:
        logger.error(f"Plivo API error initiating call: {e}")
        raise CallControlError(f"Plivo API error: {e!s}")

async def _plivo_merge_calls(
    original_call_id: str,
    new_call_id: str,
    conference_name: str | None,
    base_url: str | None,
) -> dict:
    """Placeholder — merging handled automatically when supervisor answers."""
    conference_room = conference_name or f"transfer_{original_call_id}"
    logger.info(
        f"Plivo merge prepared: waiting for supervisor to answer to join {conference_room}"
    )

    return {
        "status": "pending",
        "action": "merge_calls",
        "conference_room": conference_room,
        "provider": "plivo",
        "note": "Conference will be created automatically when supervisor answers",
    }