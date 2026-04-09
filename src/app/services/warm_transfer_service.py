"""Utilities for orchestrating warm-transfer cleanup and notifications."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.constants import (
    CUSTOMER_DISCONNECT_MESSAGE,
    SUPERVISOR_DISCONNECT_MESSAGE_BUSY,
    SUPERVISOR_DISCONNECT_MESSAGE_ENDED,
    SUPERVISOR_DISCONNECT_MESSAGE_NO_ANSWER,
    SUPERVISOR_DISCONNECT_MESSAGE_TIMEOUT,
    WARM_TRANSFER_CONFERENCE_PREFIX,
    WARM_TRANSFER_SPEECH_BUFFER_SECONDS,
    WARM_TRANSFER_SPEECH_CHARS_PER_SECOND,
    WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY,
    WARM_TRANSFER_TIMEOUT_SECONDS,
)
from app.managers.session_manager import SessionManager

# Local registry for timeout tasks on this pod instance
# Key: session_id, Value: asyncio.Task
# Note: This is only for local cancellation - the real timeout state is in MongoDB
_local_timeout_tasks: dict[str, asyncio.Task] = {}


def cancel_warm_transfer_timeout(session_id: str) -> bool:
    """Cancel an active warm transfer timeout task (local pod only).
    
    This cancels the local asyncio task if it exists on this pod.
    The database state (warm_transfer_timeout_at) is cleared separately.
    
    Returns True if a local timeout was cancelled, False otherwise.
    """
    task = _local_timeout_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"[WarmTransfer] Cancelled local timeout task for session {session_id}")
        return True
    return False


async def mark_warm_transfer_timeout_cancelled(
    session_id: str,
    tenant_id: str,
) -> bool:
    """Mark warm transfer timeout as cancelled in the database.
    
    This is called when supervisor joins or disconnects, so that even if
    the timeout task runs on a different pod, it will see the transfer is no longer active.
    
    Returns True if timeout was marked cancelled, False on error.
    """
    try:
        from app.db.database import MongoClient, get_database
        
        client = MongoClient.get_client()
        db = get_database(tenant_id, client)
        session_manager = SessionManager(db)
        
        await session_manager.update_session_fields(
            session_id=session_id,
            updates={
                "metadata.warm_transfer_timeout_at": None,
            }
        )
        logger.info(f"[WarmTransfer] Cleared timeout deadline in DB for session {session_id}")
        return True
    except Exception as exc:
        logger.warning(f"[WarmTransfer] Failed to clear timeout deadline in DB: {exc}")
        return False


async def start_warm_transfer_timeout(
    session_id: str,
    tenant_id: str,
    original_call_uuid: str,
    supervisor_call_uuid: str | None,
    timeout_seconds: int = WARM_TRANSFER_TIMEOUT_SECONDS,
) -> None:
    """Start a timeout task for warm transfer.
    
    If the supervisor doesn't join within the timeout, the customer will be
    notified and the call will be cleaned up.
    
    This is MULTI-POD SAFE:
    1. Stores timeout deadline in MongoDB (warm_transfer_timeout_at)
    2. When timeout fires, checks database to verify transfer is still active
    3. Other pods can cancel by clearing warm_transfer_active in database
    """
    # Cancel any existing local timeout for this session
    cancel_warm_transfer_timeout(session_id)
    
    # Calculate and store the timeout deadline in database
    timeout_at = datetime.now(timezone.utc).timestamp() + timeout_seconds
    
    try:
        from app.db.database import MongoClient, get_database
        
        client = MongoClient.get_client()
        db = get_database(tenant_id, client)
        session_manager = SessionManager(db)
        
        await session_manager.update_session_fields(
            session_id=session_id,
            updates={
                "metadata.warm_transfer_timeout_at": timeout_at,
                "metadata.warm_transfer_original_call_uuid": original_call_uuid,
                "metadata.warm_transfer_supervisor_call_uuid": supervisor_call_uuid,
            }
        )
        logger.info(f"[WarmTransfer] Stored timeout deadline in DB: {timeout_at} for session {session_id}")
    except Exception as exc:
        logger.error(f"[WarmTransfer] Failed to store timeout deadline in DB: {exc}")
        # Continue anyway - the local timeout task will still work on this pod
    
    async def timeout_handler():
        try:
            logger.info(f"[WarmTransfer] Starting timeout ({timeout_seconds}s) for session {session_id}")
            await asyncio.sleep(timeout_seconds)
            
            # Timeout expired - check database to see if warm transfer is still active
            # This is CRITICAL for multi-pod: another pod may have already handled the disconnect
            from app.db.database import MongoClient, get_database
            
            client = MongoClient.get_client()
            db = get_database(tenant_id, client)
            session_manager = SessionManager(db)
            session = await session_manager.get_session(session_id)
            
            if not session:
                logger.warning(f"[WarmTransfer] Timeout fired but session {session_id} not found")
                return
            
            metadata = session.metadata or {}
            warm_transfer_active = metadata.get("warm_transfer_active", False)
            stored_timeout_at = metadata.get("warm_transfer_timeout_at")
            
            # Check if warm transfer is still active AND timeout wasn't cancelled
            if not warm_transfer_active:
                logger.info(f"[WarmTransfer] Timeout fired but warm transfer already completed for session {session_id}")
                return
            
            if stored_timeout_at is None:
                logger.info(f"[WarmTransfer] Timeout fired but timeout was cancelled (cleared in DB) for session {session_id}")
                return
            
            # Double-check: if the stored timeout is different, another pod may have restarted the timeout
            if abs(stored_timeout_at - timeout_at) > 5:  # Allow 5 second tolerance
                logger.info(f"[WarmTransfer] Timeout mismatch - another pod may have restarted timeout. "
                           f"Expected {timeout_at}, found {stored_timeout_at}")
                return
            
            # Warm transfer is still active - supervisor didn't answer in time
            logger.warning(
                f"[WarmTransfer] TIMEOUT: Supervisor didn't answer within {timeout_seconds}s for session {session_id}"
            )
            
            # Get the actual call UUIDs from database (in case they were updated)
            actual_original_call_uuid = metadata.get("warm_transfer_original_call_uuid") or metadata.get("original_call_uuid") or original_call_uuid
            actual_supervisor_call_uuid = metadata.get("warm_transfer_supervisor_call_uuid") or metadata.get("supervisor_call_uuid") or supervisor_call_uuid
            
            # Get Plivo client and handle timeout
            from app.core import settings
            import plivo
            
            if not settings.PLIVO_AUTH_ID or not settings.PLIVO_AUTH_TOKEN:
                logger.error(f"[WarmTransfer] Plivo credentials not configured for timeout handling")
                return
                
            plivo_client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
            
            conference_name = f"{WARM_TRANSFER_CONFERENCE_PREFIX}{session_id}"
            timeout_message = metadata.get("supervisor_disconnect_prompts", {}).get("timeout") or SUPERVISOR_DISCONNECT_MESSAGE_TIMEOUT
            
            # IMPORTANT: Stop hold music before speaking the message
            # This ensures the customer can clearly hear the message
            if actual_original_call_uuid:
                try:
                    await asyncio.to_thread(plivo_client.calls.stop_playing, actual_original_call_uuid)
                    logger.info(f"[WarmTransfer] Stopped hold music before timeout message for call {actual_original_call_uuid}")
                    await asyncio.sleep(0.5)  # Brief pause for audio to stop
                except Exception as exc:
                    logger.warning(f"[WarmTransfer] Could not stop hold music: {exc}")
            
            # Try to speak to customer in conference
            spoken = False
            try:
                await asyncio.to_thread(
                    plivo_client.conferences.member_speak,
                    conference_name,
                    "all",
                    timeout_message,
                )
                spoken = True
                logger.info(f"[WarmTransfer] Spoke timeout message to customer in conference {conference_name}")
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Failed to speak to conference {conference_name}: {exc}")
                # Try direct call speak as fallback
                if actual_original_call_uuid:
                    try:
                        await asyncio.to_thread(
                            plivo_client.calls.speak,
                            actual_original_call_uuid,
                            text=timeout_message,
                        )
                        spoken = True
                    except Exception as exc2:
                        logger.warning(f"[WarmTransfer] Failed to speak to call {actual_original_call_uuid}: {exc2}")
            
            if spoken:
                # Wait for message to be spoken
                estimated_duration = (len(timeout_message) / WARM_TRANSFER_SPEECH_CHARS_PER_SECOND) + WARM_TRANSFER_SPEECH_BUFFER_SECONDS
                await asyncio.sleep(max(WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY, estimated_duration))
            
            # Hang up supervisor call if it exists
            if actual_supervisor_call_uuid:
                try:
                    await asyncio.to_thread(plivo_client.calls.hangup, actual_supervisor_call_uuid)
                    logger.info(f"[WarmTransfer] Hung up supervisor call {actual_supervisor_call_uuid}")
                except Exception as exc:
                    logger.warning(f"[WarmTransfer] Failed to hang up supervisor call: {exc}")
            
            # Hang up conference members (customer)
            try:
                await asyncio.to_thread(
                    plivo_client.conferences.member_hangup,
                    conference_name,
                    "all",
                )
                logger.info(f"[WarmTransfer] Hung up conference members in {conference_name}")
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Failed to hang up conference members: {exc}")
                # Try direct call hangup
                if actual_original_call_uuid:
                    try:
                        await asyncio.to_thread(plivo_client.calls.hangup, actual_original_call_uuid)
                    except Exception as exc2:
                        logger.warning(f"[WarmTransfer] Failed to hang up call {actual_original_call_uuid}: {exc2}")
            
            # Clear warm transfer metadata
            updates = {
                "metadata.warm_transfer_active": False,
                "metadata.supervisor_call_uuid": None,
                "metadata.transfer_completed": True,
                "metadata.supervisor_phone_number": None,
                "metadata.warm_transfer_timeout": True,
                "metadata.warm_transfer_timeout_at": None,
                "metadata.warm_transfer_original_call_uuid": None,
                "metadata.warm_transfer_supervisor_call_uuid": None,
            }
            try:
                await session_manager.update_session_fields(session_id=session_id, updates=updates)
                logger.info(f"[WarmTransfer] Cleared metadata after timeout for session {session_id}")
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Failed to clear metadata after timeout: {exc}")
            
        except asyncio.CancelledError:
            logger.info(f"[WarmTransfer] Timeout task cancelled for session {session_id}")
        except Exception as exc:
            logger.error(f"[WarmTransfer] Error in timeout handler for session {session_id}: {exc}", exc_info=True)
        finally:
            # Remove from local registry
            _local_timeout_tasks.pop(session_id, None)
    
    # Create and store the timeout task locally
    task = asyncio.create_task(timeout_handler())
    _local_timeout_tasks[session_id] = task
    logger.info(f"[WarmTransfer] Started timeout task for session {session_id}")


async def handle_supervisor_disconnect(
    session_manager: SessionManager,
    session_id: str,
    original_call_uuid: str | None,
    metadata: dict[str, Any],
    disconnect_reason: str,
    speak_to_call_func: Callable[[str, str], Awaitable[None]] | None = None,
    hangup_call_func: Callable[[str], Awaitable[None]] | None = None,
    speak_to_conference_func: Callable[[str, str, str], Awaitable[bool]] | None = None,
    hangup_conference_member_func: Callable[[str, str], Awaitable[bool]] | None = None,
    stop_playing_func: Callable[[str], Awaitable[None]] | None = None,
    tenant_id: str | None = None,
) -> None:
    """Notify caller and tidy metadata when supervisor leg ends the transfer.
    
    When the customer is in a conference (after being transferred), we must use
    conference-aware APIs to speak to them and hang up, as regular call.speak()
    doesn't work for calls in a conference.
    """
    # Cancel any active timeout task for this session (local pod)
    cancel_warm_transfer_timeout(session_id)
    
    # Also clear timeout state in database (for multi-pod environments)
    if tenant_id:
        await mark_warm_transfer_timeout_cancelled(session_id, tenant_id)

    if not speak_to_call_func or not hangup_call_func:
        raise ValueError("speak_to_call_func and hangup_call_func are required")

    message_map = {
        "busy": SUPERVISOR_DISCONNECT_MESSAGE_BUSY,
        "no_answer": SUPERVISOR_DISCONNECT_MESSAGE_NO_ANSWER,
        "ended": SUPERVISOR_DISCONNECT_MESSAGE_ENDED,
    }
    disconnect_message = metadata.get("supervisor_disconnect_prompts", {}).get(disconnect_reason) or message_map.get(
        disconnect_reason, SUPERVISOR_DISCONNECT_MESSAGE_ENDED
    )

    # Conference name where the customer is located (after being transferred)
    conference_name = f"{WARM_TRANSFER_CONFERENCE_PREFIX}{session_id}"
    
    if original_call_uuid:
        spoken = False
        hung_up = False
        
        # IMPORTANT: Stop hold music before speaking the message
        # This ensures the customer can clearly hear the message without background audio
        if stop_playing_func:
            try:
                await stop_playing_func(original_call_uuid)
                logger.info(f"[WarmTransfer] Stopped hold music before disconnect message for call {original_call_uuid}")
                await asyncio.sleep(0.5)  # Brief pause for audio to stop
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Could not stop hold music: {exc}")
        
        # Try conference API first (customer is likely in a conference after transfer)
        if speak_to_conference_func and hangup_conference_member_func:
            logger.info(f"[WarmTransfer] Attempting to speak to customer in conference {conference_name}")
            spoken = await speak_to_conference_func(conference_name, "all", disconnect_message)
            
            if spoken:
                logger.info(f"[WarmTransfer] Successfully spoke to customer in conference {conference_name}")
                estimated_duration = (len(disconnect_message) / WARM_TRANSFER_SPEECH_CHARS_PER_SECOND) + WARM_TRANSFER_SPEECH_BUFFER_SECONDS
                await asyncio.sleep(max(WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY, estimated_duration))
                
                # Hang up all members in the conference
                hung_up = await hangup_conference_member_func(conference_name, "all")
                if hung_up:
                    logger.info(f"[WarmTransfer] Successfully hung up conference {conference_name} members")
        
        # Fallback to regular call API if conference API fails or is not available
        if not spoken:
            logger.info(f"[WarmTransfer] Conference speak failed or not available, trying direct call API")
            try:
                await speak_to_call_func(original_call_uuid, disconnect_message)
                spoken = True
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Failed to speak to call {original_call_uuid}: {exc}")
        
        if spoken and not hung_up:
            estimated_duration = (len(disconnect_message) / WARM_TRANSFER_SPEECH_CHARS_PER_SECOND) + WARM_TRANSFER_SPEECH_BUFFER_SECONDS
            await asyncio.sleep(max(WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY, estimated_duration))
            try:
                await hangup_call_func(original_call_uuid)
            except Exception as exc:
                logger.warning(f"[WarmTransfer] Failed to hang up call {original_call_uuid}: {exc}")

    updates = {
        "metadata.warm_transfer_active": False,
        "metadata.supervisor_call_uuid": None,
        "metadata.transfer_completed": True,
        "metadata.supervisor_phone_number": None,
    }

    try:
        await session_manager.update_session_fields(session_id=session_id, updates=updates)
        logger.info(f"[WarmTransfer] Cleared metadata after supervisor disconnect for session {session_id}")
    except Exception as exc:
        logger.warning(f"[WarmTransfer] Failed to update metadata after supervisor disconnect: {exc}")


async def handle_customer_disconnect(
    session_manager: SessionManager,
    session_id: str,
    supervisor_call_uuid: str | None,
    metadata: dict[str, Any],
    speak_to_call_func: Callable[[str, str], Awaitable[None]] | None = None,
    hangup_call_func: Callable[[str], Awaitable[None]] | None = None,
    tenant_id: str | None = None,
) -> None:
    """Notify supervisor that the caller has left and clean up warm-transfer metadata."""
    # Cancel any active timeout task for this session (local pod)
    cancel_warm_transfer_timeout(session_id)
    
    # Also clear timeout state in database (for multi-pod environments)
    if tenant_id:
        await mark_warm_transfer_timeout_cancelled(session_id, tenant_id)

    if not speak_to_call_func:
        raise ValueError("speak_to_call_func is required")

    if not supervisor_call_uuid:
        logger.debug("[WarmTransfer] No supervisor call UUID to notify for customer disconnect (session %s)", session_id)
        return

    disconnect_message = metadata.get("customer_disconnect_message") or CUSTOMER_DISCONNECT_MESSAGE

    try:
        await speak_to_call_func(supervisor_call_uuid, disconnect_message)
        estimated_duration = (len(disconnect_message) / WARM_TRANSFER_SPEECH_CHARS_PER_SECOND) + WARM_TRANSFER_SPEECH_BUFFER_SECONDS
        await asyncio.sleep(max(WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY, estimated_duration))
    except Exception as exc:
        logger.warning(f"[WarmTransfer] Failed to speak customer disconnect message: {exc}")

    if hangup_call_func:
        try:
            await hangup_call_func(supervisor_call_uuid)
        except Exception as exc:
            logger.warning(f"[WarmTransfer] Failed to hang up supervisor call after customer disconnect: {exc}")

    updates = {
        "metadata.warm_transfer_active": False,
        "metadata.supervisor_call_uuid": None,
        "metadata.transfer_completed": True,
        "metadata.supervisor_phone_number": None,
    }

    try:
        await session_manager.update_session_fields(session_id=session_id, updates=updates)
        logger.info(f"[WarmTransfer] Cleared metadata after customer disconnect for session {session_id}")
    except Exception as exc:
        logger.warning(f"[WarmTransfer] Failed to update metadata after customer disconnect: {exc}")

