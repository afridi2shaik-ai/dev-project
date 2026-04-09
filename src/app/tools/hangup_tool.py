import asyncio
from typing import Any

from loguru import logger
from pipecat.frames.frames import EndFrame, EndTaskFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection

# Type-hint only; not required at runtime
try:  # pragma: no cover - optional import for type hints
    from pipecat.services.llm_service import FunctionCallParams  # type: ignore
except Exception:  # pragma: no cover
    FunctionCallParams = Any  # type: ignore


async def hangup_call(params: "FunctionCallParams", parting_words: str | None = None, reason: str | None = None) -> None:
    """Use this function to end the phone call.

    This should only be called when the user explicitly says goodbye or indicates they are finished with the conversation.
    Do not use it if the user asks a question you cannot answer.
    
    CRITICAL: This function will NOT hang up if a warm transfer is in progress. The call must remain active
    until the supervisor joins the conference.

    Args:
        params: Tool invocation context provided by the LLM service.
        parting_words: The final words to say to the user before hanging up.
        reason:  reason for ending the call, for logging or transcripts.
    """
    # CRITICAL: Check if warm transfer is active - if so, refuse to hang up
    try:
        from app.tools.session_context_tool import get_session_context
        from app.managers.session_manager import SessionManager
        from app.db.database import MongoClient, get_database
        
        context = get_session_context()
        if context:
            client = MongoClient.get_client()
            db = get_database(context.user.tenant_id, client)
            session_manager = SessionManager(db)
            session = await session_manager.get_session(context.session_id)
            
            if session and session.metadata:
                metadata = session.metadata if isinstance(session.metadata, dict) else session.metadata.__dict__ if hasattr(session.metadata, '__dict__') else {}
                warm_transfer_active = metadata.get('warm_transfer_active', False)
                
                if warm_transfer_active:
                    logger.warning(f"⚠️ Hangup blocked: Warm transfer is active for session {context.session_id}. Call must remain active until supervisor joins.")
                    await params.result_callback({
                        "status": "blocked",
                        "action": "hangup",
                        "reason": "Warm transfer in progress - call cannot be hung up until transfer completes",
                        "message": "The call is being transferred to a supervisor. Please wait for the transfer to complete."
                    })
                    # Don't hang up - just return
                    return
    except Exception as e:
        logger.warning(f"⚠️ Could not check warm_transfer_active status: {e}. Proceeding with hangup.")
        # Continue with hangup if we can't check - better to allow hangup than block it incorrectly
    
    # Return a structured result first, so the assistant can acknowledge
    # and the transcript can be updated before the call ends.
    await params.result_callback({"status": "ok", "action": "hangup", "reason": reason, "parting_words": parting_words})

    # If there are parting words, speak them.
    if parting_words:
        await params.llm.push_frame(TTSSpeakFrame(parting_words))

    # Immediately push an EndFrame downstream. This acts as a "gate,"
    # preventing the LLM's final, redundant message from reaching the TTS service.
    # The TTSSpeakFrame above has already passed this point.
    await params.llm.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)

    # Wait for the parting words audio to finish playing.
    if parting_words:
        # We estimate the time needed based on the length of the text.
        # (Assuming ~15 characters/second speaking rate + 1s buffer for latency)
        estimated_speech_duration = (len(parting_words) / 15) + 1.0
        await asyncio.sleep(estimated_speech_duration)
    else:
        # If no parting words, a small delay is still good for observers.
        await asyncio.sleep(0.5)

    # Now, trigger graceful pipeline termination in the upstream direction.
    try:
        # Use EndTaskFrame instead of EndFrame to ensure proper transport disconnection
        # EndTaskFrame is converted to EndFrame by pipeline source and triggers proper termination
        await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
    except Exception:
        # If push fails, it's not critical as the main job is done.
        pass
