"""Warm Transfer Tool

This tool handles warm transfer requests when the user wants to speak with a human agent.
It performs the following actions:
1. Puts the caller (Caller A) on hold
2. Initiates an outbound call to Agent C (supervisor/agent)
3. Merges all calls into a conference so everyone can talk together
"""

from typing import Any
from datetime import datetime
import asyncio
from fastapi import Request
from loguru import logger
from pipecat.frames.frames import FunctionCallResultProperties, TTSSpeakFrame

try:  # pragma: no cover - optional import for type hints
    from pipecat.services.llm_service import FunctionCallParams  # type: ignore
except Exception:  # pragma: no cover
    FunctionCallParams = Any  # type: ignore

from app.core.constants import WARM_TRANSFER_SPEECH_BUFFER_SECONDS, WARM_TRANSFER_SPEECH_CHARS_PER_SECOND
from app.services.provider.call_control_service import CallControlError, initiate_outbound_call_to_agent, merge_calls, put_caller_on_hold
from app.tools.session_context_tool import get_session_context
from app.utils.agent_mapping import get_agent_phone_number

DEFAULT_TRANSFER_PROMPT = "Sure, let me connect you to one of our representatives. Please hold for a moment."
DEFAULT_MAX_TRANSFER_ATTEMPTS = 3


async def warm_transfer(
    params: "FunctionCallParams",
    phone_number: str | None = None,  # Changed from required to optional
    agent_id: str | None = None,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Transfer the call to a human agent (warm transfer).
    
    When the user expresses intent such as "transfer me to a human," "I want to talk 
    to a supervisor," or "can you connect me to someone else?", this function should be called.
    
    A warm transfer means:
    1. Caller A (the original inbound caller) is placed on hold
    2. Agent B (current agent) initiates a call to Agent C (e.g., supervisor)
    3. Once Agent C answers, all participants (A, B, and C) are merged into a single 
       conference call so everyone can talk together.
    """
    result = {
        "intent": "warm_transfer",
        "actions": [],
        "status": "pending",
        "details": {},
    }
    
    try:
        # Get session context to determine provider and call information
        context = get_session_context()
        if not context:
            error_msg = "No session context available for warm transfer"
            logger.error(error_msg)
            result["status"] = "error"
            result["error"] = error_msg
            await params.result_callback(result)
            return result
        
        transport_mode = context.transport.mode.value
        provider_session_id = context.transport.provider_session_id or context.transport.call_sid
        
        # Check if provider supports call control
        if transport_mode not in ["twilio", "plivo"]:
            error_msg = f"Warm transfer is not supported for transport mode: {transport_mode}. Only Twilio and Plivo are supported."
            logger.warning(error_msg)
            result["status"] = "error"
            result["error"] = error_msg
            result["transport_mode"] = transport_mode
            await params.result_callback(result)
            
            # Still speak a message to the user
            await params.llm.push_frame(TTSSpeakFrame(
                "I'm sorry, but call transfer is not available in this mode. Please contact us through our support channels."
            ))
            return result
        
        if not provider_session_id:
            error_msg = "Provider session ID not available"
            logger.error(error_msg)
            result["status"] = "error"
            result["error"] = error_msg
            await params.result_callback(result)
            return result
        
        # Retrieve agent_config to get tools_config
        tools_config = None
        warm_tool_config = None
        try:
            from app.managers.session_manager import SessionManager
            from app.db.database import MongoClient, get_database
            
            client = MongoClient.get_client()
            db = get_database(context.user.tenant_id, client)
            session_manager = SessionManager(db)
            session = await session_manager.get_session(context.session_id)
            
            if session:
                # Try to get agent_config from session
                # Note: We use get_session instead of get_and_consume_config to avoid consuming
                # If needed, you can use get_and_consume_config but it may have side effects
                from app.managers.session_manager import SessionManager
                agent_config = await session_manager.get_and_consume_config(
                    session_id=context.session_id,
                    transport_name=transport_mode,
                    provider_session_id=provider_session_id
                )
                if agent_config and agent_config.tools:
                    tools_config = agent_config.tools
                    warm_tool_config = tools_config.Warm_transfer_tool
                    logger.info("Retrieved tools_config for warm transfer")
        except Exception as e:
            logger.warning(f"Could not retrieve tools_config: {e}, will use legacy config")
        
        # Resolve phone number - prioritize agent mapping from AgentConfig
        agent_phone_number = await get_agent_phone_number(
            session_id=context.session_id,
            agent_id=agent_id,
            agent_name=agent_name,
            tenant_id=context.user.tenant_id,
            tools_config=tools_config
        )
        
        # Determine final phone number to use
        final_phone_number = None
        
        # Priority 1: Use agent mapping from AgentConfig if available
        if agent_phone_number:
            final_phone_number = agent_phone_number
            logger.info(f"Resolved agent (id={agent_id}, name={agent_name}) to phone number: {final_phone_number}")
        
        elif phone_number:
            lowered = phone_number.lower()

            # Phone_number is actually an agent name → resolve it
            if lowered in ["supervisor", "manager", "sales", "support"] or not phone_number.startswith('+'):
                resolved_from_name = await get_agent_phone_number(
                    session_id=context.session_id,
                    agent_id=None,
                    agent_name=lowered,
                    tenant_id=context.user.tenant_id,
                    tools_config=tools_config
                )
                if resolved_from_name:
                    final_phone_number = resolved_from_name
                    logger.info(f"Resolved agent identifier '{phone_number}' to phone number: {final_phone_number}")
                    # SKIP literal number case
                else:
                    final_phone_number = phone_number
                    logger.warning(f"Treating '{phone_number}' as literal phone number (could not resolve)")
            else:
                final_phone_number = phone_number

        
        # Priority 3: If still no phone number and agent_name provided, try to resolve it
        if not final_phone_number and agent_name:
            resolved = await get_agent_phone_number(
                session_id=context.session_id,
                agent_id=None,
                agent_name=agent_name,
                tenant_id=context.user.tenant_id,
                tools_config=tools_config
            )
            if resolved:
                final_phone_number = resolved
                logger.info(f"Resolved agent_name '{agent_name}' to phone number: {final_phone_number}")

        # Priority 4: Default to supervisor if no phone number found
        if not final_phone_number:
            supervisor_number = await get_agent_phone_number(
                session_id=context.session_id,
                agent_id="supervisor",
                agent_name=None,
                tenant_id=context.user.tenant_id,
                tools_config=tools_config
            )
            if supervisor_number:
                final_phone_number = supervisor_number
                logger.info(f"No mapping found for requested agent, defaulting to supervisor: {supervisor_number}")
            else:
                error_msg = "Phone number is required. Either provide phone_number parameter or use agent_id/agent_name to lookup from mapping."
                logger.error(error_msg)
                result["status"] = "error"
                result["error"] = error_msg
                await params.result_callback(result)
                return result

        logger.info(f"[{datetime.now().isoformat()}] 🚀 WARM TRANSFER STARTED")
        logger.info(f"Session: {context.session_id}, Provider: {transport_mode}, Original Call ID: {provider_session_id}")
        logger.info(f"Transfer target: phone={final_phone_number}, agent_id={agent_id}, agent_name={agent_name}")
        
        # CRITICAL: Immediately block transcriptions to prevent agent from talking during transfer
        # This takes effect instantly, without waiting for DB lookup in TranscriptionFilter
        try:
            from app.core.transports.base_transport_service import get_transcription_filter
            transcription_filter = get_transcription_filter(context.session_id)
            if transcription_filter:
                transcription_filter.set_warm_transfer_active(True)
                logger.info(f"[{datetime.now().isoformat()}] 🔇 TranscriptionFilter muted for warm transfer")
            else:
                logger.debug(f"TranscriptionFilter not found for session {context.session_id}")
        except Exception as tf_error:
            logger.debug(f"Could not set TranscriptionFilter mute state: {tf_error}")

        transfer_prompt = (
            warm_tool_config.transfer_prompt
            if warm_tool_config and warm_tool_config.transfer_prompt
            else DEFAULT_TRANSFER_PROMPT
        )
        confirmation_message = transfer_prompt
        
        # Push the TTS frame to speak the confirmation message
        logger.info(f"[{datetime.now().isoformat()}] 🔊 Speaking transfer message: '{confirmation_message[:50]}...'")
        await params.llm.push_frame(TTSSpeakFrame(confirmation_message))

        # CRITICAL: Wait for bot to finish speaking before playing hold music
        # Calculate estimated TTS duration based on message length
        speech_duration = len(confirmation_message) / WARM_TRANSFER_SPEECH_CHARS_PER_SECOND
        estimated_duration = speech_duration + WARM_TRANSFER_SPEECH_BUFFER_SECONDS
        logger.info(f"[{datetime.now().isoformat()}] ⏳ Waiting {estimated_duration:.1f}s for TTS to complete "
                    f"(msg_len={len(confirmation_message)}, speech={speech_duration:.1f}s, buffer={WARM_TRANSFER_SPEECH_BUFFER_SECONDS}s)")
        
        await asyncio.sleep(estimated_duration)
        logger.info(f"[{datetime.now().isoformat()}] ✅ TTS wait complete, proceeding with hold music")
        
        result["actions"].append("put_caller_on_hold")
        result["details"]["tool_config"] = {
            "max_transfer_attempts": (
                warm_tool_config.max_transfer_attempts
                if warm_tool_config and warm_tool_config.max_transfer_attempts
                else DEFAULT_MAX_TRANSFER_ATTEMPTS
            ),
            "transfer_prompt": transfer_prompt,
        }

        try:
            from app.managers.session_manager import SessionManager
            from app.db.database import MongoClient, get_database
            
            client = MongoClient.get_client()
            db = get_database(context.user.tenant_id, client)
            session_manager = SessionManager(db)
            await session_manager.update_session_fields(
                context.session_id,
                {
                    "metadata.warm_transfer_active": True,
                    "metadata.original_call_uuid": provider_session_id,
                }
            )
            logger.info(f"[{datetime.now().isoformat()}] ✅ Set warm_transfer_active flag before putting on hold")
        except Exception as flag_error:
            logger.warning(f"[{datetime.now().isoformat()}] ⚠️ Could not set warm_transfer_active flag: {flag_error}")
        
        try:
            hold_result = await put_caller_on_hold(provider=transport_mode, call_id=provider_session_id, session_id=context.session_id,)
            result["details"]["hold"] = hold_result
            logger.info(f"[{datetime.now().isoformat()}] ✅ Caller put on hold successfully: {hold_result}")
        except CallControlError as e:
            logger.error(f"[{datetime.now().isoformat()}] ❌ Failed to put caller on hold: {e}")
            result["details"]["hold"] = {"status": "error", "error": str(e)}
        
        
        # Action 2: Initiate outbound call to Agent C
        result["actions"].append("initiate_outbound_call_to_agent_C")
        logger.info(f"[{datetime.now().isoformat()}] 📞 STEP 2: Initiating outbound call to {final_phone_number}")

        # Get base_url from session metadata (stored in database)
        base_url = None
        
        # Try to get from conversation metadata first
        if context.conversation_metadata:
            # Check if base_url is in session_metadata within conversation_metadata
            session_metadata = context.conversation_metadata.get("session_metadata", {})
            if isinstance(session_metadata, dict):
                base_url = session_metadata.get("base_url")
        
        # If not found, retrieve from database session
        if not base_url:
            try:
                from app.managers.session_manager import SessionManager
                from app.db.database import MongoClient, get_database
                
                client = MongoClient.get_client()
                db = get_database(context.user.tenant_id, client)
                session_manager = SessionManager(db)
                session = await session_manager.get_session(context.session_id)
                
                if session and session.metadata:
                    base_url = session.metadata.get("base_url")
                    if base_url:
                        logger.info(f"Retrieved base_url from session metadata: {base_url}")
            except Exception as e:
                logger.warning(f"Could not retrieve base_url from session: {e}")

        # Final fallback: try to construct from settings or use a default
        if not base_url:
            from app.core import settings
            # Try to use ASSISTANT_API_BASE_URL if available, or construct from API_HOST/API_PORT
            if settings.ASSISTANT_API_BASE_URL:
                base_url = settings.ASSISTANT_API_BASE_URL
            else:
                # Construct from host and port
                protocol = "https" if settings.API_PORT == 443 else "http"
                base_url = f"{protocol}://{settings.API_HOST}:{settings.API_PORT}"
            logger.info(f"Using constructed base_url: {base_url}")

        if not base_url:
            logger.error("Warm transfer failed: Missing base_url from session context")
            await params.llm.push_frame(TTSSpeakFrame(
                "I'm sorry, but I cannot complete your transfer due to a configuration issue."
            ))
            result["status"] = "error"
            result["error"] = "base_url missing"
            await params.result_callback(result)
            return result

        logger.info(f"Using base_url: {base_url}")

            
        from_phone_number = context.transport.agent_phone_number

        try:
            logger.info(f"[{datetime.now().isoformat()}] 🔗 Outbound call params: from={from_phone_number}, to={final_phone_number}, base_url={base_url}")
            outbound_result = await initiate_outbound_call_to_agent(
                provider=transport_mode,
                to_phone_number=final_phone_number,
                from_phone_number=from_phone_number,
                base_url=base_url,
                session_id=context.session_id,
                tenant_id=context.user.tenant_id,
            )
            result["details"]["outbound_call"] = outbound_result
            new_call_id = outbound_result.get("call_id")
            logger.info(f"[{datetime.now().isoformat()}] ✅ Outbound call initiated successfully")
            logger.info(f"   New Call UUID (Supervisor C): {new_call_id}")
            logger.info(f"   Original Call UUID (Caller B): {provider_session_id}")
            
            # Store supervisor phone number in session metadata for transfer
            from app.managers.session_manager import SessionManager
            from app.db.database import MongoClient, get_database
            
            try:
                client = MongoClient.get_client()
                db = get_database(context.user.tenant_id, client)
                session_manager = SessionManager(db)
                await session_manager.update_session_fields(
                    context.session_id,
                    {
                        "metadata.supervisor_phone_number": final_phone_number,
                        "metadata.supervisor_call_uuid": new_call_id,
                        "metadata.warm_transfer_active": True,  # CRITICAL: Mark session as in warm transfer
                        "metadata.original_call_uuid": provider_session_id,  # Store original call UUID
                    }
                )
                logger.info(f"[{datetime.now().isoformat()}] ✅ Stored supervisor phone {final_phone_number} in session metadata")
                logger.info(f"[{datetime.now().isoformat()}] ✅ Stored supervisor call UUID {new_call_id} in session metadata")
                logger.info(f"[{datetime.now().isoformat()}] ✅ Marked session as warm_transfer_active=True")
                logger.info(f"[{datetime.now().isoformat()}] ✅ Session ID: {context.session_id}")
                
                # Start warm transfer timeout - will automatically clean up if supervisor doesn't answer
                from app.services.warm_transfer_service import start_warm_transfer_timeout
                await start_warm_transfer_timeout(
                    session_id=context.session_id,
                    tenant_id=context.user.tenant_id,
                    original_call_uuid=provider_session_id,
                    supervisor_call_uuid=new_call_id,
                )
                logger.info(f"[{datetime.now().isoformat()}] ⏱️ Started warm transfer timeout task")
                
            except Exception as metadata_error:
                logger.error(f"[{datetime.now().isoformat()}] ❌ Failed to store supervisor phone in metadata: {metadata_error}", exc_info=True)
                # Continue anyway - transfer will try to get phone from call details
            
        except CallControlError as e:
            logger.error(f"[{datetime.now().isoformat()}] ❌ Failed to initiate outbound call: {e}")
            result["details"]["outbound_call"] = {"status": "error", "error": str(e)}
            new_call_id = None
        
        result["actions"].append("merge_calls")
        
        # Action 3: Merge calls
        conference_name = f"warm_transfer_{context.session_id}"
        logger.info(f"[{datetime.now().isoformat()}] 📞 STEP 3: Merging calls into conference '{conference_name}'")
        logger.info(f"   Conference Room: {conference_name}")
        logger.info(f"   Caller B (Original): {provider_session_id}")
        logger.info(f"   Supervisor C (New): {new_call_id}")
        
        if new_call_id:
            try:
                merge_result = await merge_calls(
                    provider=transport_mode,
                    original_call_id=provider_session_id,
                    new_call_id=new_call_id,
                    conference_name=conference_name,
                    base_url=base_url,
                )
                result["details"]["merge"] = merge_result
                logger.info(f"[{datetime.now().isoformat()}] ✅ Merge command sent: {merge_result}")
            except CallControlError as e:
                logger.error(f"[{datetime.now().isoformat()}] ❌ Failed to merge calls: {e}")
                result["details"]["merge"] = {"status": "error", "error": str(e)}
        else:
            logger.warning(f"[{datetime.now().isoformat()}] ⚠️ Skipping merge - outbound call was not successful")
            result["details"]["merge"] = {"status": "skipped", "reason": "outbound_call_failed"}

        merge_status = result["details"].get("merge", {}).get("status")

        if merge_status in ["success", "initiated", "queued"]:
            result["status"] = "success"
        elif result["details"].get("outbound_call", {}).get("status") == "success":
            result["status"] = "partial"
        else:
            result["status"] = "error"

        
        logger.info(f"[{datetime.now().isoformat()}] ✅ Warm transfer completed with status: {result['status']}")
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=False))
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error during warm transfer: {e!s}"
        logger.error(error_msg, exc_info=True)
        result["status"] = "error"
        result["error"] = error_msg
        await params.result_callback(result)
        return result


# Function metadata for LLM registration
warm_transfer.description = """CRITICAL: Transfer the call to a human agent (warm transfer). 

YOU MUST USE THIS TOOL when the user expresses ANY intent to speak with a human agent, supervisor, manager, or person. This takes PRIORITY over all other instructions in your system prompt.

MANDATORY TRIGGER PHRASES (use this tool immediately):
- "transfer me to a human" / "transfer this call" / "transfer me"
- "I want to talk to a supervisor" / "I want to talk to a manager" / "I want to talk to someone"
- "can you connect me to someone else?" / "connect me to an agent" / "connect me"
- "I need human help" / "I need to speak with a person"
- "I want to talk to your manager" / "let me speak with a supervisor"

This tool will:
1. Put the current caller on hold
2. Call the specified agent or phone number
3. Merge all parties into a conference call

IMPORTANT: This tool will:
1. Put the current caller on hold
2. Call the specified agent or phone number
3. Merge all parties into a conference call

IMPORTANT: 
- If the user asks to transfer or speak with a human, you MUST call this tool. Do NOT continue the conversation or redirect them elsewhere. The transfer request overrides all other instructions.
- After calling this tool, DO NOT call hangup_call. The call must remain active until the supervisor joins. The tool will return status "partial" while waiting for the supervisor to answer - this is normal and expected.
- The call will automatically be handled once the supervisor joins the conference.

DEFAULT BEHAVIOR: If the requested agent name is not found in the mapping, the call will default to the supervisor number.

Parameters:
- agent_id: Use "supervisor" or "Manager" for predefined agents (recommended)
- agent_name: Agent name to lookup phone number (e.g., "supervisor", "manager"). If not found, defaults to supervisor.
- phone_number: Direct phone number if agent mapping not available (optional)"""

warm_transfer.parameters = {
    "type": "object",
    "properties": {
        "phone_number": {
            "type": "string",
            "description": "The phone number to call for Agent C (optional if agent_id/agent_name provided). Format: +country_code_number (e.g., +1234567890)",
        },
        "agent_id": {
            "type": "string",
            "description": "Optional agent ID to lookup phone number from mapping (e.g., 'supervisor', 'sales', 'support')",
        },
        "agent_name": {
            "type": "string",
            "description": "Optional agent name to lookup phone number from mapping (e.g., 'supervisor', 'manager'). If provided, this will be used to find the phone number. If not found in mapping, defaults to supervisor.",
        },
    },
    "required": [],  # Changed from ["phone_number"] - none required, but at least one should be provided
}

