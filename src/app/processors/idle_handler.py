import asyncio
import inspect
from typing import Any

from loguru import logger
from pipecat.frames.frames import EndTaskFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection

from app.schemas.services.agent import IdleTimeoutConfig


async def _fetch_session_metadata_from_processor(processor) -> dict[str, Any]:
    """Retrieve the latest session metadata using any helper the processor exposes."""
    # Prefer a supplier function that always pulls fresh metadata (if provided)
    metadata_supplier = getattr(processor, "_session_metadata_supplier", None)
    if metadata_supplier:
        try:
            metadata_candidate = metadata_supplier()
            metadata = await metadata_candidate if inspect.isawaitable(metadata_candidate) else metadata_candidate
            if isinstance(metadata, dict):
                return metadata
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Unable to fetch session metadata via supplier: {exc}")

    # Fallback to direct session lookup if session manager handles are attached
    session_manager = getattr(processor, "_session_manager", None)
    session_id = getattr(processor, "_session_id", None)

    if session_manager and session_id:
        try:
            session = await session_manager.get_session(session_id)
            metadata_obj = getattr(session, "metadata", None) if session else None
            if isinstance(metadata_obj, dict):
                return metadata_obj
            if hasattr(metadata_obj, "model_dump"):
                return metadata_obj.model_dump()
            if hasattr(metadata_obj, "__dict__"):
                return dict(metadata_obj.__dict__)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Unable to fetch session metadata via session manager: {exc}")

    return {}


async def _should_pause_for_warm_transfer(processor) -> bool:
    """Determine if idle handling should pause because a warm transfer is active."""
    metadata = await _fetch_session_metadata_from_processor(processor)
    if metadata.get("warm_transfer_active"):
        logger.debug("Skipping idle handler — warm transfer is active for this session")
        # Keep retry counters stable so we don't exhaust retries during the transfer hold period
        try:
            if getattr(processor, "_retry_count", 0) > 0:
                processor._retry_count -= 1
        except AttributeError:
            pass
        return True
    return False


async def handle_user_idle(processor, retry_count: int, config: IdleTimeoutConfig, llm_service=None, hangup_observer=None):
    """
    Handles user idle events with escalating prompts.
    
    Args:
        processor: The UserIdleProcessor instance
        retry_count: Current retry attempt number
        config: IdleTimeoutConfig with timeout settings
        llm_service: Optional LLM service reference for proper frame handling
        hangup_observer: Optional HangupObserver reference for setting hangup reason
    """
    logger.info(f"User idle detected - retry #{retry_count}/{config.retries}")

    # During warm transfers the caller is deliberately on hold. Pause idle prompts so
    # they don't hear "Are you still there?" while we connect the supervisor.
    if await _should_pause_for_warm_transfer(processor):
        return True

    # For outbound calls, voicemail detection uses a TTS gate that can block idle prompts.
    # We temporarily disable that gate while speaking each idle prompt, then re-enable it
    # afterwards unless voicemail was detected in the meantime.
    voicemail_gate = getattr(processor, "_voicemail_gate", None)
    voicemail_detected_event = getattr(processor, "_voicemail_detected_event", None)

    async def _speak_idle_text(text: str):
        # Disable gate just for the duration of the idle prompt audio.
        gate_was_modified = False
        if voicemail_gate and hasattr(voicemail_gate, "_gating_active"):
            try:
                voicemail_gate._gating_active = False
                gate_was_modified = True
            except Exception:
                # If the gate internals change, avoid failing idle handling.
                gate_was_modified = False

        await processor.push_frame(TTSSpeakFrame(text), FrameDirection.UPSTREAM)

        # Re-enable gate after estimated TTS playback duration.
        # Use a background task so idle monitoring can continue.
        if gate_was_modified:
            estimated_speech_duration = (len(text) / 15) + 1.0

            async def _reenable_gate_after_prompt():
                await asyncio.sleep(estimated_speech_duration)
                if voicemail_detected_event is not None and voicemail_detected_event.is_set():
                    # Voicemail override is active; don't undo its TTS gating state.
                    return
                if voicemail_gate and hasattr(voicemail_gate, "_gating_active"):
                    try:
                        voicemail_gate._gating_active = True
                        # Clear any buffered frames to avoid leaking stale audio controls.
                        if hasattr(voicemail_gate, "_frame_buffer"):
                            voicemail_gate._frame_buffer = []
                    except Exception:
                        pass

            asyncio.create_task(_reenable_gate_after_prompt())

    if retry_count < config.retries:
        # Send idle prompt and continue monitoring
        prompt_index = retry_count - 1
        prompt = config.prompt_templates[prompt_index]

        logger.info(f"Sending idle prompt #{retry_count}: '{prompt}'")
        await _speak_idle_text(prompt)
        return True  # Continue monitoring
    else:
        # If retries are exhausted, send the final message and end the call
        logger.info("Idle retries exhausted, ending conversation and disconnecting call")
        final_prompt_index = min(config.retries - 1, len(config.prompt_templates) - 1)
        final_prompt = config.prompt_templates[final_prompt_index]
        logger.info(f"Sending final prompt: '{final_prompt}'")
        await _speak_idle_text(final_prompt)
        
        # Wait for the final prompt audio to finish playing
        # Estimate: ~15 characters/second speaking rate + 1s buffer for latency
        estimated_speech_duration = (len(final_prompt) / 15) + 1.0
        await asyncio.sleep(estimated_speech_duration)

        # Capture hangup time on idle termination if available
        try:
            # Try to get hangup_observer from parameter first, then from processor attribute
            observer = hangup_observer or getattr(processor, "_hangup_observer", None)
            if observer:
                if hasattr(observer, "set_reason_idle_timeout"):
                    await observer.set_reason_idle_timeout()
                elif hasattr(observer, "set_reason_client_disconnected"):
                    # Fallback for backward compatibility
                    await observer.set_reason_client_disconnected()
        except Exception as e:
            logger.error(f"Unable to set hangup time on idle termination: {e}", exc_info=True)

        # Use EndTaskFrame instead of EndFrame to ensure proper transport disconnection
        # EndTaskFrame is converted to EndFrame by pipeline source and triggers proper termination
        logger.info("Pushing EndTaskFrame to trigger call disconnection due to idle timeout")
        await processor.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
        return False  # Stop monitoring
