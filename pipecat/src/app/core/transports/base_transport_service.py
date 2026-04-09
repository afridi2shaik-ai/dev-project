import asyncio
import datetime
from dataclasses import dataclass
from typing import Any

import aiohttp
from loguru import logger
from opentelemetry import baggage, trace
from pipecat.frames.frames import BotStoppedSpeakingFrame, CancelFrame, EndFrame, LLMRunFrame, OutputTransportMessageFrame, TTSSpeakFrame
from pipecat.observers.loggers.user_bot_latency_log_observer import UserBotLatencyLogObserver
from pipecat.observers.turn_tracking_observer import TurnTrackingObserver
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.transcript_processor import TranscriptionUpdateFrame, TranscriptProcessor
from pipecat.utils.tracing.turn_trace_observer import TurnTraceObserver

from app.agents import BaseAgent
from app.core.observers import AppObserver, HangupObserver, MetricsLogger, PlottingObserver, SessionLogObserver, SummarizationObserver
from app.core.pipeline_builder import build_audio_chat_pipeline, build_enhanced_multimodal_pipeline, build_enhanced_traditional_pipeline
from app.db.database import get_database
from app.managers.artifact_manager import ArtifactManager
from app.managers.customer_profile_manager import CustomerProfileManager
from app.managers.log_manager import LogManager
from app.managers.session_manager import SessionManager
from app.schemas.core.customer_profile import CallSummary as ProfileCallSummary
from app.schemas.log_schema import SessionState
from app.schemas.services.agent import ModelGeneratedMessageConfig, PipelineMode, SpeakFirstMessageConfig
from app.schemas.session_schema import Session
from app.services.customer_profile_service import CustomerProfileService
from app.utils.transcript_utils import TranscriptAccumulator
from app.utils.summary_utils import generate_summary


@dataclass
class PipelineServices:
    """A dataclass to hold all the service and observer instances for a pipeline."""

    metrics_logger: MetricsLogger
    session_log_observer: SessionLogObserver
    summarization_observer: SummarizationObserver
    turn_tracking_observer: TurnTrackingObserver
    hangup_observer: HangupObserver
    plotting_observer: PlottingObserver
    app_observer: AppObserver
    transcript_accumulator: TranscriptAccumulator


# Global dictionary to track artifact managers by session ID
_artifact_managers: dict[str, Any] = {}

# Global dictionary to track transcription filters by session ID
# Used by warm_transfer_tool to immediately block transcriptions during warm transfer
_transcription_filters: dict[str, Any] = {}


def get_transcription_filter(session_id: str) -> Any | None:
    """Get the TranscriptionFilter instance for a session.
    
    Used by warm_transfer_tool to immediately set warm_transfer_active
    for instant transcription blocking without waiting for DB lookup.
    
    Args:
        session_id: The session ID
        
    Returns:
        TranscriptionFilter instance or None if not found
    """
    return _transcription_filters.get(session_id)


def _register_transcription_filter(session_id: str, filter_instance: Any):
    """Register a TranscriptionFilter for a session."""
    _transcription_filters[session_id] = filter_instance
    logger.debug(f"Registered TranscriptionFilter for session {session_id}")


def _unregister_transcription_filter(session_id: str):
    """Unregister a TranscriptionFilter for a session."""
    if session_id in _transcription_filters:
        del _transcription_filters[session_id]
        logger.debug(f"Unregistered TranscriptionFilter for session {session_id}")


async def _save_artifacts_for_session(session_id: str, final_session: Session) -> bool:
    """
    Save artifacts for a session from outside the pipeline.
    This is called by the session manager when the session state changes.
    
    Args:
        session_id: The session ID
        final_session: The final session object with updated state
        
    Returns:
        bool: True if artifacts were saved, False otherwise
    """
    logger.info(f"🔄 External request to save artifacts for session {session_id}")

    # Check if we have an artifact manager for this session
    artifact_manager = _artifact_managers.get(session_id)
    if not artifact_manager:
        logger.warning(f"⚠️ No artifact manager found for session {session_id}")
        return False

    try:
        # Get the tenant ID from the session
        tenant_id = final_session.metadata.get("tenant_id") if final_session.metadata else None
        if not tenant_id:
            logger.warning(f"⚠️ No tenant ID found for session {session_id}")
            return False

        # Get the database
        db = get_database(tenant_id)
        log_manager = LogManager(db)

        # Save artifacts using the artifact manager
        await artifact_manager.save_artifacts(
            final_session=final_session,
            agent=None,  # We don't have the agent here, but it's only needed for config
            initial_metadata={},
            raw_audio_payload=None,
            error_details=None,
        )

        logger.info(f"✅ Artifacts saved externally for session {session_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving artifacts externally for session {session_id}: {e}", exc_info=True)
        return False


async def run_pipeline(transport, agent: BaseAgent, session_id: str, tenant_id: str, provider_session_id: str, transport_name: str, pipeline_params: PipelineParams, metadata: dict, handle_sigint: bool = False):
    metadata = metadata or {}
    raw_audio_payload: dict[str, Any] | None = None
    error_details: dict | None = None
    stt = llm = tts = context_aggregator = transcript_processor = audiobuffer = None
    background_tasks: set[asyncio.Task] = set()
    # Tasks that must NOT be cancelled during teardown (e.g., post-call enrichment / profile updates).
    # These should be able to finish even after the pipeline ends.
    post_call_tasks: set[asyncio.Task] = set()
    call_summary: dict | None = None
    # NOTE: We no longer track actual_call_end_time here - it's tracked by HangupObserver
    # The HangupObserver captures the exact time when hangup_call tool is executed
    # or when client disconnects, ensuring accurate call duration (not cleanup time)

    # Helper function to shutdown websocket-based services properly.
    # Defined early so it's available even if setup fails.
    async def shutdown_websocket_services(services_list, session_id_for_logging):
        """Disable reconnect and cancel websocket services to prevent dangling tasks."""
        for service in services_list:
            if not service:
                continue

            service_name = type(service).__name__

            # Disable reconnect loop for websocket services
            if hasattr(service, '_reconnect_on_error'):
                logger.debug(f"🔌 Disabling reconnect for {service_name} in session {session_id_for_logging}")
                service._reconnect_on_error = False

            # Cancel service to stop websocket tasks (receive/keepalive loops)
            if hasattr(service, 'cancel'):
                try:
                    logger.debug(f"🛑 Cancelling {service_name} in session {session_id_for_logging}")
                    # Use timeout to avoid hanging during shutdown
                    await asyncio.wait_for(service.cancel(CancelFrame()), timeout=2.0)
                    logger.debug(f"✅ Successfully cancelled {service_name}")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Timeout cancelling {service_name} - may leave dangling tasks")
                except Exception as e:
                    logger.warning(f"⚠️ Error cancelling {service_name}: {type(e).__name__}")

    span = trace.get_current_span()
    trace_id = span.get_span_context().trace_id
    metadata["trace_id"] = f"{trace_id:032x}"

    baggage.set_baggage("tenant_id", tenant_id)
    db = get_database(tenant_id)
    session_manager = SessionManager(db)
    log_manager = LogManager(db)

    session = await session_manager.get_session(session_id)
    if not session:
        logger.error(f"Cannot run pipeline, session not found for id: {session_id}")
        return

    user_phone: str | None = None
    user_email: str | None = None
    if session and session.metadata:
        user_email = session.metadata.get("user_email") or session.metadata.get("email")
    try:
        if session and getattr(session, "created_by", None):
            user_email = user_email or getattr(session.created_by, "email", None)
    except Exception:
        pass

    updates = {}
    if not session.provider_session_id:
        updates["provider_session_id"] = provider_session_id

    # Build call_data structure for phone calls (for context building)
    call_data = None
    if transport_name in ["twilio", "plivo"]:
        # Extract direction using participant order (reference implementation approach)
        actual_direction = None  # Don't default yet - will infer if needed

        # First, try to get direction from session metadata (stored during outbound call creation)
        if session and session.metadata:
            session_direction = session.metadata.get("call_direction")
            if session_direction:
                actual_direction = session_direction.strip().lower()
                # Normalize outbound-api -> outbound
                if actual_direction == "outbound-api":
                    actual_direction = "outbound"
                logger.debug(f"{transport_name} call direction from session metadata: {actual_direction}")
            elif transport_name == "plivo":
                # Fallback: some providers may include a direction field in the inbound webhook payload
                inbound_request = session.metadata.get("inbound_http_request", {})
                webhook_direction = inbound_request.get("Direction")
                if webhook_direction:
                    actual_direction = str(webhook_direction).strip().lower()
                    logger.debug(f"Plivo call direction from inbound webhook payload: {actual_direction}")

        # If still no direction, infer from participant order (reference implementation approach)
        if not actual_direction and session and session.participants:
            # For outbound calls, system participant is first (index 0)
            # For inbound calls, user participant is first (index 0)
            if session.participants[0].role.value == "system":
                actual_direction = "outbound"
                logger.debug("Inferred direction as 'outbound' from participant order (SYSTEM first)")
            else:
                actual_direction = "inbound"
                logger.debug("Inferred direction as 'inbound' from participant order (USER first)")
        elif not actual_direction:
            actual_direction = "inbound"  # Final fallback
            logger.warning("No session metadata or participants available, defaulting to 'inbound'")

        # Extract phone numbers from session participants
        from_number = None
        to_number = None
        
        if session and session.participants:
            for participant in session.participants:
                if participant.role.value == "user" and participant.phone_number:
                    if actual_direction == "inbound":
                        from_number = participant.phone_number  # User called us
                    else:
                        to_number = participant.phone_number    # We called user
                elif participant.role.value == "system" and participant.phone_number:
                    if actual_direction == "inbound":
                        to_number = participant.phone_number    # Our phone (user called us)
                    else:
                        from_number = participant.phone_number  # Our phone (we called user)
            logger.debug(f"🔍 Extracted phone numbers from participants: from={from_number}, to={to_number}")

        # Fallback: try to get from metadata if not found in participants
        if not from_number or not to_number:
            if isinstance(metadata, dict):
                from_number = metadata.get("start", {}).get("from") or from_number
                to_number = metadata.get("start", {}).get("to") or to_number

        if actual_direction == "inbound":
            user_phone = from_number or user_phone
        else:
            user_phone = to_number or user_phone

        call_data = {
            "start": {
                "direction": actual_direction,
                "from": from_number,
                "to": to_number,
                "callSid": provider_session_id,
                "accountSid": metadata.get("start", {}).get("accountSid") if isinstance(metadata, dict) else None,
            }
        }
        logger.info(f"📞 Call direction determined: {actual_direction} (session_id: {session_id})")
        logger.debug(f"🔍 Call data structure: {call_data}")
    else:
        # Non-telephony transports may still provide email in metadata
        if isinstance(metadata, dict):
            user_email = metadata.get("user_email") or metadata.get("email") or user_email

    # Resolve customer profile context for the session
    profile_context = None
    language_preference_override = None
    try:
        profile_service = CustomerProfileService(db, tenant_id)
        profile_context = await profile_service.enrich_session_context(
            transport_type=transport_name,
            user_phone=user_phone,
            user_email=user_email,
        )
        if profile_context:
            # Check if language from profile is enabled in config
            use_lang_from_profile = agent.config.customer_profile_config.use_language_from_profile
            
            if use_lang_from_profile:
                language_preference_override = profile_context.get("language_preference")
                if language_preference_override:
                    metadata.setdefault("language_preference_override", language_preference_override)
            metadata.setdefault(
                "customer_profile",
                {
                    "profile_found": profile_context.get("profile_found"),
                    "profile_id": profile_context.get("profile_id"),
                    "language_preference": language_preference_override,
                    "context_string": profile_context.get("context_string"),
                    "brief_context": profile_context.get("brief_context"),
                    "customer_name": profile_context.get("customer_name"),
                    "total_calls": profile_context.get("total_calls"),
                },
            )
    except Exception as profile_error:
        logger.warning(f"Unable to resolve customer profile context: {profile_error}")

    if metadata:
        if session.metadata:
            merged_metadata = {**session.metadata, **metadata}
        else:
            merged_metadata = metadata
        updates["metadata"] = merged_metadata

    if updates:
        await session_manager.update_session_fields(session_id, updates)

    aiohttp_session = aiohttp.ClientSession()
    try:
        # Clear any leftover pre-request cache at the start of a new session
        try:
            if hasattr(agent, "clear_pre_request_cache"):
                agent.clear_pre_request_cache()
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear pre-request cache for session {session_id}: {e}")

        # Set session context with call data for phone calls
        await agent.set_session_context(
            session_id=session_id,
            transport_name=transport_name,
            db=db,
            tenant_id=tenant_id,
            provider_session_id=provider_session_id,
            user_details=None,  # Will be extracted from session if available
            transport_metadata=metadata,
            call_data=call_data
        )

        stt, llm, tts, context_aggregator, messages = await agent.get_services(aiohttp_session, db, tenant_id)

        # Enable turn-based audio so we can capture audio even when user/bot don't overlap
        audiobuffer = AudioBufferProcessor(enable_turn_audio=True)

        # Accumulate per-turn audio segments in the order they occur
        turn_segments: list[tuple[str, bytes]] = []

        transcript_processor = TranscriptProcessor()
        transcript_accumulator = TranscriptAccumulator()

        @transcript_processor.event_handler("on_transcript_update")
        async def on_transcript_update(processor, frame: TranscriptionUpdateFrame):
            for message in frame.messages:
                transcript_accumulator.add_message(message)

        user_idle_processor = None
        transcription_filter = None  # Will be set for traditional mode to block transcriptions during warm transfer
        voicemail_detector = None  # Only set for TRADITIONAL; must exist so on_client_connected can reference it for all modes
        if agent.config.pipeline_mode == PipelineMode.TRADITIONAL:
            # Use enhanced pipeline builder with advanced features from reference implementation
            # Includes improved transcription filtering and better frame handling

            # CRITICAL: VoicemailDetector should ONLY be used for outbound telephony calls
            # Using it for WebRTC/WebSocket will cause TTSGate to block all audio output
            is_telephony_transport = transport_name in ("plivo", "twilio")
            voicemail_detector = agent._voicemail_detector if is_telephony_transport else None

            if agent._voicemail_detector and not is_telephony_transport:
                logger.info(f"⏭️ Skipping VoicemailDetector for non-telephony transport: {transport_name}")

            pipeline, audiobuffer, user_idle_processor, transcription_filter = build_enhanced_traditional_pipeline(
                transport,
                stt,
                llm,
                tts,
                context_aggregator,
                agent.config,
                transcript_processor,
                voicemail_detector=voicemail_detector,
                transport_name=transport_name,
            )
        elif agent.config.pipeline_mode == PipelineMode.MULTIMODAL:
            # Use enhanced multimodal pipeline with advanced features from reference implementation
            pipeline, audiobuffer, user_idle_processor, transcription_filter = build_enhanced_multimodal_pipeline(transport, llm, context_aggregator, agent.config, transcript_processor)
        elif agent.config.pipeline_mode == PipelineMode.AUDIO_CHAT:
            # Voice in, text out: STT → LLM only (no TTS)
            pipeline, audiobuffer, user_idle_processor, transcription_filter = build_audio_chat_pipeline(
                transport,
                stt,
                llm,
                context_aggregator,
                agent.config,
                transcript_processor,
                hangup_observer=None,
                transcript_accumulator=transcript_accumulator,
            )
        else:
            raise ValueError(f"Unsupported pipeline mode: {agent.config.pipeline_mode}")
        
        # Set session context on TranscriptionFilter for warm transfer blocking
        # This allows the filter to check session metadata and block transcriptions during warm transfer
        if transcription_filter:
            async def get_session_metadata():
                """Supplier function to get current session metadata."""
                try:
                    sess = await session_manager.get_session(session_id)
                    if sess and sess.metadata:
                        return sess.metadata if isinstance(sess.metadata, dict) else {}
                except Exception:
                    pass
                return {}
            
            transcription_filter.set_session_context(
                session_manager=session_manager,
                session_id=session_id,
                metadata_supplier=get_session_metadata
            )
            
            # Register the filter globally for immediate access by warm_transfer_tool
            _register_transcription_filter(session_id, transcription_filter)
            logger.debug(f"TranscriptionFilter configured with session context for warm transfer blocking")

        # Setup turn tracking
        turn_tracking_observer = TurnTrackingObserver()

        # Create all pipeline services using the dataclass for better organization
        services = PipelineServices(
            metrics_logger=MetricsLogger(pipeline, transport_name, session_id),
            session_log_observer=SessionLogObserver(transport_name, session_id),
            summarization_observer=SummarizationObserver(transport_name, session_id, transcript_accumulator),
            turn_tracking_observer=turn_tracking_observer,
            hangup_observer=HangupObserver(session_id, transcript_accumulator),
            plotting_observer=PlottingObserver(),
            app_observer=AppObserver(transcript_accumulator),
            transcript_accumulator=transcript_accumulator,
        )

        task = PipelineTask(
            pipeline,
            params=pipeline_params,
            observers=[
                services.metrics_logger,
                services.session_log_observer,
                services.summarization_observer,
                services.turn_tracking_observer,
                services.hangup_observer,
                services.plotting_observer,
                services.app_observer,
                UserBotLatencyLogObserver(),
                TurnTraceObserver(turn_tracker=turn_tracking_observer),
            ],
        )

        # CRITICAL FIX: Make the task accessible to LLM service for hangup functionality
        if hasattr(llm, "_set_task"):
            llm._set_task(task)
        else:
            # Create the reference directly if _set_task doesn't exist
            llm._task = task

        # Used to coordinate voicemail override with idle prompts.
        # If voicemail is detected while an idle prompt is being spoken, we should avoid
        # re-enabling TTSGate after that prompt finishes.
        voicemail_detected_event = asyncio.Event()

        # Register voicemail detection handlers (only for telephony transports)
        # CRITICAL: Only register handlers when voicemail detector is actually in the pipeline
        # VoicemailDetector is now configured with 2.0s aggregation timeout to handle streaming STT properly
        is_telephony_transport = transport_name in ("plivo", "twilio")
        if agent._voicemail_detector and is_telephony_transport:
            @agent._voicemail_detector.event_handler("on_voicemail_detected")
            async def on_voicemail_detected(processor):
                voicemail_detected_event.set()
                logger.info(f"📞 Voicemail detected for session {session_id} - treating as definitive voicemail")

                # Stop idle processor to prevent "Are you still there?" messages
                if user_idle_processor:
                    logger.info(f"🛑 Stopping idle processor for voicemail session {session_id}")
                    user_idle_processor._interrupted = True
                    await user_idle_processor._stop()

                # ConversationGate is permanently closed for voicemail - no fallback to conversation
                logger.info(f"🚫 ConversationGate closed - voicemail mode active")

                # Use the pipeline LLM to generate voicemail message with agent's system prompt
                from pipecat.frames.frames import LLMMessagesAppendFrame

                user_prompt = agent.config.voicemail_detector.user_prompt
                logger.info(f"📝 Generating voicemail message for session {session_id}")

                await llm.queue_frame(LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": user_prompt}],
                    run_llm=True
                ))

                # Wait for message to be spoken (LLM generates → TTS speaks → audio output)
                # We use a reasonable timeout for the voicemail message to be delivered
                # The voicemail message should be brief (<30 words as per the prompt)
                await asyncio.sleep(15)
                
                logger.info(f"✅ Voicemail message delivered, ending call for session {session_id}")
                
                # Record the reason for hangup
                if services.hangup_observer:
                    await services.hangup_observer.set_reason_voicemail()
                
                # End the call gracefully
                await task.queue_frame(EndFrame())

        # Create ArtifactManager for centralized artifact management
        artifact_manager = ArtifactManager(
            session_id=session_id,
            tenant_id=tenant_id,
            transport_name=transport_name,
            provider_session_id=provider_session_id,
            log_manager=log_manager,
            metrics_logger=services.metrics_logger,
            session_log_observer=services.session_log_observer,
            plotting_observer=services.plotting_observer,
            hangup_observer=services.hangup_observer,
            transcript_accumulator=services.transcript_accumulator,
        )

        @audiobuffer.event_handler("on_audio_data")
        async def on_audio_data(buffer, audio, sample_rate, num_channels):
            nonlocal raw_audio_payload
            raw_audio_payload = {"audio": audio, "sample_rate": sample_rate, "num_channels": num_channels}
            # Enhanced logging for audio data events
            recording_state = getattr(audiobuffer, '_recording', False)
            user_buf_size = len(getattr(audiobuffer, "_user_audio_buffer", bytearray()))
            bot_buf_size = len(getattr(audiobuffer, "_bot_audio_buffer", bytearray()))
            logger.debug(f"🎵 Audio data event: session={session_id}, recording={recording_state}, sample_rate={sample_rate}, audio_size={len(audio)}, user_buf={user_buf_size}, bot_buf={bot_buf_size}")

        @audiobuffer.event_handler("on_user_turn_audio_data")
        async def on_user_turn_audio_data(buffer, audio, sample_rate, num_channels):
            # Capture user turn audio as-is (mono)
            if audio:
                turn_segments.append(("user", bytes(audio)))
                logger.debug(f"🎤 User turn audio captured: session={session_id}, audio_size={len(audio)}, sample_rate={sample_rate}")

        @audiobuffer.event_handler("on_bot_turn_audio_data")
        async def on_bot_turn_audio_data(buffer, audio, sample_rate, num_channels):
            # Capture bot turn audio as-is (mono)
            if audio:
                turn_segments.append(("bot", bytes(audio)))
                logger.debug(f"🔊 Bot turn audio captured: session={session_id}, audio_size={len(audio)}, sample_rate={sample_rate}")

        # Store the artifact manager in the global dictionary for potential later use.
        # This allows external calls to _save_artifacts_for_session to work.
        _artifact_managers[session_id] = artifact_manager

        session_metadata_cache: dict | None = None

        async def _get_session_metadata(force_refresh: bool = False) -> dict:
            nonlocal session_metadata_cache
            if session_metadata_cache is not None and not force_refresh:
                return session_metadata_cache

            try:
                session_snapshot = await session_manager.get_session(session_id)
            except Exception as metadata_error:
                logger.warning(f"⚠️ Unable to load session metadata for {session_id}: {metadata_error}")
                session_metadata_cache = {}
                return session_metadata_cache

            metadata_obj = getattr(session_snapshot, "metadata", None) if session_snapshot else None
            if isinstance(metadata_obj, dict):
                session_metadata_cache = dict(metadata_obj)
            elif hasattr(metadata_obj, "model_dump"):
                session_metadata_cache = metadata_obj.model_dump()
            elif hasattr(metadata_obj, "__dict__"):
                session_metadata_cache = dict(metadata_obj.__dict__)
            else:
                session_metadata_cache = {}
            return session_metadata_cache

        async def _get_session_metadata_fresh() -> dict:
            """Always fetch the latest session metadata (no caching)."""
            return await _get_session_metadata(force_refresh=True)

        async def _mark_first_message_played():
            metadata = await _get_session_metadata()
            if metadata.get("first_message_played"):
                return
            metadata["first_message_played"] = True
            try:
                await session_manager.update_session_fields(session_id, {"metadata.first_message_played": True})
            except Exception as metadata_error:
                logger.warning(f"Failed to persist first_message_played flag for {session_id}: {metadata_error}")

        # Configure idle processor dependencies (hangup observer + session metadata access)
        if user_idle_processor:
            user_idle_processor._hangup_observer = services.hangup_observer
            user_idle_processor._session_manager = session_manager
            user_idle_processor._session_id = session_id
            user_idle_processor._session_metadata_supplier = _get_session_metadata_fresh
            # Provide voicemail gate + event so idle prompts can temporarily bypass TTSGate
            # without breaking voicemail override.
            if voicemail_detector and hasattr(voicemail_detector, "_voicemail_gate"):
                user_idle_processor._voicemail_gate = voicemail_detector._voicemail_gate
                user_idle_processor._voicemail_detected_event = voicemail_detected_event
            logger.debug(f"⚙️ Configured UserIdleProcessor hooks for session {session_id}")

        def _build_language_pref_hint():
            """Return language preference and hint string from cached customer profile."""
            # Check if language from profile is enabled in config
            if not agent.config.customer_profile_config.use_language_from_profile:
                return None, None
            
            customer_profile = getattr(agent, "_customer_profile", None)
            if not customer_profile:
                return None, None

            ai_data = customer_profile.ai_extracted_data or {}
            ai_lang = ai_data.get("language_preference")
            explicit_lang = customer_profile.language_preference

            language_pref = ai_lang or explicit_lang
            if language_pref:
                return language_pref, f"Please respond in {language_pref}."
            return None, None

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            # CRITICAL: Start recording AFTER StartFrame has been processed (which happens when client connects)
            # This ensures sample rate is initialized before we start recording
            try:
                # Check sample rate to ensure StartFrame has been processed
                sample_rate = getattr(audiobuffer, '_sample_rate', 0)
                if sample_rate == 0:
                    logger.warning(f"⚠️ Sample rate not initialized yet for session {session_id}, waiting for StartFrame...")
                    # Wait a bit for StartFrame to be processed
                    await asyncio.sleep(0.1)
                    sample_rate = getattr(audiobuffer, '_sample_rate', 0)
                
                recording_state = getattr(audiobuffer, '_recording', False)
                if not recording_state:
                    await audiobuffer.start_recording()
                    recording_state_after = getattr(audiobuffer, '_recording', False)
                    if recording_state_after:
                        logger.info(f"✅ Audio recording started for session {session_id} (sample_rate={sample_rate}, after StartFrame)")
                    else:
                        logger.error(f"❌ Failed to start recording for session {session_id} - _recording flag is False")
                else:
                    logger.debug(f"Audio recording already active for session {session_id} (sample_rate={sample_rate})")
            except Exception as e:
                logger.error(f"❌ Failed to start audio recording in on_client_connected for session {session_id}: {e}", exc_info=True)

            first_message_config = agent.config.first_message
            metadata = await _get_session_metadata()
            first_message_already_played = metadata.get("first_message_played", False)

            # Check if voicemail detector is active in the pipeline (telephony + enabled)
            voicemail_gate_active = (
                voicemail_detector is not None 
                and hasattr(voicemail_detector, '_voicemail_gate')
                and voicemail_detector._voicemail_gate is not None
            )
            
            # Determine if we need to bypass the TTSGate for the first message
            # Only needed for "bot speaks first" modes (speak_first, model_generated)
            # For wait_for_user mode, the gate should remain active since user speaks first
            bot_speaks_first = isinstance(first_message_config, (SpeakFirstMessageConfig, ModelGeneratedMessageConfig))
            needs_gate_bypass = voicemail_gate_active and bot_speaks_first and not first_message_already_played

            if first_message_already_played:
                logger.info(f"⏭️ Skipping first_message for session {session_id} (already delivered earlier in this call)")
            else:
                # For speak-first/model-generated with voicemail detection:
                # We temporarily disable TTSGate gating to allow the initial greeting through
                # After the first message completes, we re-enable gating for classification
                first_message_complete = asyncio.Event()
                
                if needs_gate_bypass:
                    # Temporarily disable the gate to allow first message through
                    logger.info(f"📞 Temporarily disabling TTSGate for first message (voicemail detection active)")
                    voicemail_detector._voicemail_gate._gating_active = False
                    
                    # Set up a one-time handler to detect when first message finishes
                    def create_callback(event):
                        async def _on_first_message_complete(frame):
                            try:
                                if isinstance(frame, BotStoppedSpeakingFrame):
                                    event.set()
                            except Exception as e:
                                logger.error(f"Error in callback: {e}, frame type: {type(frame)}")
                                raise
                        return _on_first_message_complete

                    # Register temporary observer on the task
                    services.app_observer._first_message_callback = create_callback(first_message_complete)
                
                if isinstance(first_message_config, SpeakFirstMessageConfig):
                    if agent.config.pipeline_mode != PipelineMode.AUDIO_CHAT:
                        # TRADITIONAL (voice-to-voice): send first message as transcript text and as TTS
                        await task.queue_frames([
                            OutputTransportMessageFrame(
                                message={"role": "assistant", "text": first_message_config.text}
                            ),
                            TTSSpeakFrame(text=first_message_config.text),
                        ])
                        await _mark_first_message_played()
                    else:
                        # Audio-chat has no TTS; send first message as text so it appears in transcript/chat UI
                        await task.queue_frames([
                            OutputTransportMessageFrame(
                                message={"role": "assistant", "text": first_message_config.text}
                            )
                        ])
                        await _mark_first_message_played()
                elif isinstance(first_message_config, ModelGeneratedMessageConfig):
                    if first_message_config.prompt:
                        lang_pref, lang_hint = _build_language_pref_hint()
                        prompt = first_message_config.prompt
                        if lang_hint:
                            prompt = f"{prompt}\n\n{lang_hint}"
                            logger.info(f"🌐 Applying language preference hint to first message: {lang_pref}")
                        messages.append({"role": "system", "content": prompt})
                        await task.queue_frames([LLMRunFrame()])
                        await _mark_first_message_played()
                
                # Wait for first message to complete (only if we bypassed the gate)
                if needs_gate_bypass:
                    try:
                        # Wait for first message to complete speaking (with timeout)
                        await asyncio.wait_for(first_message_complete.wait(), timeout=30.0)
                        logger.info(f"📞 First message complete for voicemail classification")
                    except asyncio.TimeoutError:
                        logger.warning(f"⚠️ Timeout waiting for first message to complete")
                    finally:
                        # Check if classification decision has been made (CONVERSATION or VOICEMAIL)
                        # If CONVERSATION was detected, the gate should stay OPEN (don't re-enable)
                        # If no decision yet, re-enable gate for ongoing classification
                        classification_made = (
                            hasattr(voicemail_detector, '_classification_processor') and
                            hasattr(voicemail_detector._classification_processor, '_decision_made') and
                            voicemail_detector._classification_processor._decision_made
                        )
                        
                        if classification_made:
                            # Classification already made - keep the gate in its current state
                            # (opened by conversation_notifier or closed by voicemail_notifier)
                            logger.info(f"📞 Classification already made, keeping TTSGate in current state (active={voicemail_detector._voicemail_gate._gating_active})")
                        else:
                            # No classification yet. Re-enable the gate so the voicemail detector
                            # can continue gating TTS while it waits for a real user signal.
                            #
                            # Idle prompts will temporarily bypass this gate during the prompt
                            # audio playback (coordinated via idle_handler.py).
                            logger.info("📞 No classification yet, re-enabling TTSGate for voicemail classification")
                            voicemail_detector._voicemail_gate._gating_active = True
                            voicemail_detector._voicemail_gate._frame_buffer = []  # Clear any stale frames
                        
                        # Remove the temporary callback
                        if hasattr(services.app_observer, '_first_message_callback'):
                            services.app_observer._first_message_callback = None

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            # Import datetime here to avoid Python closure scoping issues
            import datetime

            # We no longer need to track actual_call_end_time here
            # Instead, set the disconnection reason in the hangup observer FIRST
            # This will automatically capture the exact disconnect time
            await services.hangup_observer.set_reason_client_disconnected()

            # Add detailed logging for debugging duration calculation
            # Using the time captured by the hangup observer for consistency
            created_at = session.created_at
            hangup_time = services.hangup_observer.hangup_time

            # Make created_at timezone-aware if needed for duration calculation
            if created_at and hangup_time:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.UTC)
                duration_seconds = (hangup_time - created_at).total_seconds()
            else:
                duration_seconds = None

            logger.info(f"🔌 Client disconnected for session {session_id} at {hangup_time.isoformat()}, initiating immediate cleanup.")
            # Sanity check: if duration seems abnormally long (e.g., > 1 hour), fallback to current time
            if duration_seconds is not None and duration_seconds > 3600:
                logger.warning(f"⚠️ Unreasonable duration computed ({duration_seconds}s). Falling back to current time for end timestamp.")
                import datetime
                hangup_time = datetime.datetime.now(datetime.UTC)
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.UTC)
                duration_seconds = (hangup_time - created_at).total_seconds() if created_at else None

            logger.info(f"⏱️ Call duration calculation: created_at={created_at.isoformat() if created_at else None}, end_time={hangup_time.isoformat()}, duration={duration_seconds} seconds")

            # Log recording state before pushing EndFrame (which will stop recording)
            recording_state_before_end = getattr(audiobuffer, '_recording', False)
            sample_rate_before_end = getattr(audiobuffer, '_sample_rate', 0)
            has_audio_before_end = audiobuffer.has_audio() if hasattr(audiobuffer, 'has_audio') else False
            logger.info(f"📤 Pushing EndFrame to complete pipeline for session {session_id} (recording={recording_state_before_end}, sample_rate={sample_rate_before_end}, has_audio={has_audio_before_end})")

            # Push EndFrame downstream to signal pipeline termination
            # This mirrors the reference implementation behaviour and lets all processors
            # see a terminal frame before we cancel the task.
            if pipeline:
                from pipecat.frames.frames import EndFrame
                await pipeline.queue_frame(EndFrame(reason="client_disconnected"))

            # Shutdown websocket services before force-cancelling the pipeline
            # This prevents dangling tasks and reconnect loops
            logger.info(f"🛑 Shutting down websocket services for session {session_id} before force cancel")
            await shutdown_websocket_services([stt, llm, tts, context_aggregator, transcript_processor, audiobuffer], session_id)

            # Cancel the task immediately for quick termination
            if task and not task.has_finished():
                logger.warning(f"⚠️ Force cancelling pipeline for session {session_id} after client disconnect")
                await task.cancel()
                logger.info(f"✅ Pipeline cancel requested for session {session_id}")

            # Note: We do NOT call end_session or save_artifacts here.
            # The try/finally around runner.run(task) will handle that with the
            # captured end_time from hangup_observer, preventing duplicate work.

        runner = PipelineRunner(handle_sigint=handle_sigint, force_gc=True)
        final_session: Session | None = None
        
        # Log initial state before pipeline execution
        # Note: Recording will start in on_client_connected AFTER StartFrame is processed
        initial_sample_rate = getattr(audiobuffer, '_sample_rate', 0)
        initial_recording_state = getattr(audiobuffer, '_recording', False)
        logger.info(f"🎬 Pipeline starting for session {session_id}: sample_rate={initial_sample_rate}, recording={initial_recording_state} (will start after StartFrame)")
        
        try:
            logger.info(f"🚀 Starting PipelineRunner for session {session_id}")

            # Run pipeline - will complete when EndFrame flows through the sink
            await runner.run(task)
            logger.info(f"✅ PipelineRunner.run() completed successfully for session {session_id}")

            # Give processors a brief moment to finish any asynchronous EndFrame cleanup
            await asyncio.sleep(0.25)
            logger.debug(f"⏳ Waited for EndFrame processing to settle for session {session_id}")

            # CRITICAL: Check if warm transfer is active before ending session
            # If warm transfer is active, keep the session alive until supervisor joins
            session = await session_manager.get_session(session_id)
            warm_transfer_active = False
            if session and session.metadata:
                metadata = session.metadata if isinstance(session.metadata, dict) else session.metadata.__dict__ if hasattr(session.metadata, '__dict__') else {}
                warm_transfer_active = metadata.get('warm_transfer_active', False)
            
            if warm_transfer_active:
                logger.info(f"🔄 Warm transfer active for session {session_id} - keeping session alive until supervisor joins")
                logger.info(f"📋 Session will be closed when supervisor answers at /conference-join")
                # Don't end the session - it will be closed when /conference-join closes the WebSocket
                # The pipeline task will remain active, keeping the call alive with hold music
                return  # Exit early, don't end the session
            
            # Use hangup time from HangupObserver if available (from hangup_call tool or client disconnect)
            # Otherwise use current time (for natural pipeline completion without explicit hangup)
            end_time = services.hangup_observer.hangup_time or datetime.datetime.now(datetime.UTC)
            logger.debug(f"Pipeline ended naturally, using end_time: {end_time.isoformat()} (from_hangup: {services.hangup_observer.hangup_time is not None})")

            # Determine final state based on hangup reason
            # Use VOICEMAIL state if the call was detected as voicemail
            final_state = SessionState.COMPLETED
            hangup_reason = getattr(services.hangup_observer, "reason", None)
            if hangup_reason == "voicemail":
                final_state = SessionState.VOICEMAIL
                logger.info(f"✅ Session {session_id} ended with VOICEMAIL state (voicemail detected)")

            # End the session with appropriate state
            final_session = await session_manager.end_session(
                session_id,
                final_state=final_state,
                end_time=end_time,
                save_artifacts=False  # We'll save artifacts once in the finally block
            )
            logger.info(f"✅ Session {session_id} ended successfully")
        except asyncio.CancelledError:
            logger.info(f"Pipeline for session {session_id} was cancelled.")
            
            # CRITICAL: Check if warm transfer is active before ending session
            # If warm transfer is active, don't end the session - keep call alive
            session = await session_manager.get_session(session_id)
            warm_transfer_active = False
            if session and session.metadata:
                metadata = session.metadata if isinstance(session.metadata, dict) else session.metadata.__dict__ if hasattr(session.metadata, '__dict__') else {}
                warm_transfer_active = metadata.get('warm_transfer_active', False)
            
            if warm_transfer_active:
                logger.info(f"🔄 Warm transfer active - keeping session {session_id} alive (call on hold)")
                # Don't end the session - it will be closed when transferring to conference
                return  # Exit early, don't end the session or hang up
            
            # Use hangup time from HangupObserver if available, otherwise use current time
            end_time = services.hangup_observer.hangup_time or datetime.datetime.now(datetime.UTC)
            logger.debug(f"Pipeline cancelled, using end_time: {end_time.isoformat()} (from_hangup: {services.hangup_observer.hangup_time is not None})")

            if not final_session:
                # Session was cancelled (likely by disconnect handler)
                # Determine final state based on hangup reason
                final_state = SessionState.COMPLETED
                hangup_reason = getattr(services.hangup_observer, "reason", None)
                if hangup_reason == "voicemail":
                    final_state = SessionState.VOICEMAIL
                    logger.info(f"✅ Session {session_id} ended with VOICEMAIL state (voicemail detected)")

                # End session with captured time and appropriate state
                final_session = await session_manager.end_session(
                    session_id,
                    final_state=final_state,
                    end_time=end_time,
                    save_artifacts=False  # We'll save artifacts once in the finally block
                )
        except Exception as e:
            import traceback
            logger.error(f"Pipeline encountered an error: {e}", exc_info=True)
            error_details = {"error": str(e), "traceback": traceback.format_exc()}

            # Use hangup time from HangupObserver if available, otherwise use current time
            end_time = services.hangup_observer.hangup_time or datetime.datetime.now(datetime.UTC)
            logger.debug(f"Pipeline error occurred, using end_time: {end_time.isoformat()} (from_hangup: {services.hangup_observer.hangup_time is not None})")

            final_session = await session_manager.end_session(
                session_id,
                final_state=SessionState.ERROR,
                end_time=end_time,
                save_artifacts=False  # We'll save artifacts once in the finally block
            )
        finally:
            logger.info(f"Pipeline finished for session {session_id}. Saving artifacts.")

            # This is the single place where artifacts are saved (after end_session)
            # Ensures all session data is complete before artifact generation
            try:
                # Stop audio recording to flush any remaining buffers
                try:
                    if audiobuffer:
                        # Comprehensive logging before stopping
                        recording_state_before_stop = getattr(audiobuffer, '_recording', False)
                        sample_rate_before_stop = getattr(audiobuffer, '_sample_rate', 0)
                        has_audio_before_stop = audiobuffer.has_audio() if hasattr(audiobuffer, 'has_audio') else False
                        user_buf_before = len(getattr(audiobuffer, "_user_audio_buffer", bytearray()))
                        bot_buf_before = len(getattr(audiobuffer, "_bot_audio_buffer", bytearray()))
                        turn_segments_count = len(turn_segments)
                        
                        logger.info(f"🎵 Audio capture summary for session {session_id} before stop: recording={recording_state_before_stop}, sample_rate={sample_rate_before_stop}, has_audio={has_audio_before_stop}, user_buf={user_buf_before}, bot_buf={bot_buf_before}, turn_segments={turn_segments_count}, raw_audio_payload={'exists' if raw_audio_payload else 'None'}")
                        
                        if recording_state_before_stop:
                            logger.info(f"🛑 Stopping audio recording for session {session_id}")
                            await audiobuffer.stop_recording()
                            # Verify recording stopped
                            recording_state_after_stop = getattr(audiobuffer, '_recording', False)
                            if not recording_state_after_stop:
                                logger.info(f"✅ Audio recording stopped successfully for session {session_id}")
                            else:
                                logger.warning(f"❌ Audio recording stop called but _recording flag is still True for session {session_id}")
                        else:
                            logger.warning(f"❌ Audio recording was NOT active when stop_recording() called for session {session_id} - this may indicate recording never started")
                        
                        # Log buffer state immediately after stopping
                        try:
                            has_audio_after = audiobuffer.has_audio()
                            user_buf_after = len(getattr(audiobuffer, "_user_audio_buffer", bytearray()))
                            bot_buf_after = len(getattr(audiobuffer, "_bot_audio_buffer", bytearray()))
                            logger.info(f"🎵 Audio capture summary for session {session_id} after stop: has_audio={has_audio_after}, user_buf={user_buf_after}, bot_buf={bot_buf_after}")
                        except Exception as e:
                            logger.debug(f"Could not check audio buffer state for session {session_id}: {e}")
                except Exception as e:
                    logger.error(f"❌ Error stopping audio recording for session {session_id}: {e}", exc_info=True)
                    # Continue - we still want to save artifacts even if stop_recording fails

                # If final_session is None, try to get it one more time
                if not final_session:
                    final_session = await session_manager.get_session(session_id)

                # If merged audio wasn't produced, build a mono stream from per-turn segments
                if raw_audio_payload is None and turn_segments:
                    try:
                        sr = audiobuffer.sample_rate or 8000
                        if sr == 0:
                            logger.warning(f"⚠️ Sample rate is 0 when building audio from turn segments for session {session_id}, using default 8000")
                            sr = 8000
                        # Insert 200ms of silence between turns for clarity
                        silence = b"\x00" * int(sr * 0.2) * 2
                        combined = bytearray()
                        for _, seg_audio in turn_segments:
                            combined.extend(seg_audio)
                            combined.extend(silence)
                        raw_audio_payload = {"audio": bytes(combined), "sample_rate": sr, "num_channels": 1}
                        logger.info(f"🎧 Built audio from {len(turn_segments)} turn segments for session {session_id} (sample_rate={sr}, total_size={len(combined)})")
                    except Exception as e:
                        logger.error(f"❌ Failed to build audio from turn segments for session {session_id}: {e}", exc_info=True)

                # Save artifacts directly through the artifact manager
                if raw_audio_payload is None:
                    # Provide comprehensive context when no audio is captured
                    rec_flag = getattr(audiobuffer, "_recording", False) if audiobuffer else False
                    sample_rate_flag = getattr(audiobuffer, '_sample_rate', 0) if audiobuffer else 0
                    has_audio_flag = False
                    user_buf_size = 0
                    bot_buf_size = 0
                    try:
                        if audiobuffer:
                            has_audio_flag = audiobuffer.has_audio() if hasattr(audiobuffer, 'has_audio') else False
                            user_buf_size = len(getattr(audiobuffer, "_user_audio_buffer", bytearray()))
                            bot_buf_size = len(getattr(audiobuffer, "_bot_audio_buffer", bytearray()))
                    except Exception:
                        pass
                    logger.warning(f"⚠️ No audio captured for session {session_id}; proceeding without audio artifact. recording={rec_flag}, sample_rate={sample_rate_flag}, has_audio={has_audio_flag}, user_buf={user_buf_size}, bot_buf={bot_buf_size}, turn_segments={len(turn_segments)}")
                await artifact_manager.save_artifacts(
                    final_session=final_session,
                    agent=agent,
                    initial_metadata=metadata,
                    raw_audio_payload=raw_audio_payload,
                    error_details=error_details,
                )
                logger.info(f"✅ Artifacts saved for session {session_id}.")

                # Mark this session as having saved artifacts to prevent duplicate saves
                if not hasattr(session_manager, "_artifacts_saved_for_session"):
                    session_manager._artifacts_saved_for_session = {}
                session_manager._artifacts_saved_for_session[session_id] = True
            except Exception as e:
                logger.error(f"❌ Error saving artifacts for session {session_id}: {e}", exc_info=True)

        # --- Customer Profile Recording (Async) ---
        try:
            update_profiles = getattr(getattr(agent.config, "customer_profile_config", None), "update_after_call", False)
            if update_profiles:
                summary_messages = services.summarization_observer.messages
                call_summary = call_summary or await generate_summary(summary_messages, agent.config)

                if final_session:
                    # Extract summary_text robustly - LLM may return various formats
                    # No hard rule on structure - handle whatever we get gracefully
                    def _safe_extract_summary_text(summary_data: Any) -> str:
                        """Safely extract summary text from any LLM response format."""
                        try:
                            if not summary_data:
                                return "Call completed"
                            if isinstance(summary_data, str):
                                return summary_data
                            if not isinstance(summary_data, dict):
                                return str(summary_data)
                            
                            # Try common keys - order doesn't matter, just find something
                            for key in ["summary", "summary_text", "text", "assistant_message", "content", "response", "message"]:
                                if key in summary_data:
                                    val = summary_data[key]
                                    if isinstance(val, str) and val.strip():
                                        return val
                                    elif isinstance(val, dict):
                                        # Try to extract from nested dict
                                        for inner_key in ["text", "content", "message", "summary"]:
                                            if inner_key in val and isinstance(val[inner_key], str):
                                                return val[inner_key]
                            
                            # Fallback: find any reasonably long string value
                            for v in summary_data.values():
                                if isinstance(v, str) and len(v) > 10:
                                    return v
                            
                            # Last resort: convert to string representation
                            import json as json_mod
                            return json_mod.dumps(summary_data, ensure_ascii=False, default=str)
                        except Exception as e:
                            logger.debug(f"Summary text extraction fallback: {e}")
                            return "Call completed"
                    
                    def _safe_extract_outcome(summary_data: Any) -> str | None:
                        """Safely extract outcome from any format."""
                        try:
                            if isinstance(summary_data, dict):
                                return summary_data.get("outcome") or summary_data.get("result") or summary_data.get("status")
                        except Exception:
                            pass
                        return None
                    
                    summary_text = _safe_extract_summary_text(call_summary) if call_summary else "Call completed"
                    summary_outcome = _safe_extract_outcome(call_summary)

                    if summary_text:
                        customer_name = None
                        if session and session.participants:
                            for participant in session.participants:
                                if participant.role.value == "user" and participant.name:
                                    customer_name = participant.name
                                    break
                        if session and session.metadata:
                            customer_name = customer_name or session.metadata.get("user_name") or session.metadata.get("name")

                        identifier = None
                        identifier_type = None
                        if user_phone:
                            from app.utils.validation.field_validators import normalize_phone_identifier

                            identifier = normalize_phone_identifier(user_phone) or user_phone
                            identifier_type = "phone"
                        if user_email and not identifier:
                            identifier = user_email
                            identifier_type = "email"

                        if identifier and identifier_type:
                            duration_seconds = None
                            if final_session.created_at and final_session.end_time:
                                duration_seconds = int((final_session.end_time - final_session.created_at).total_seconds())

                            call_outcome = summary_outcome or (final_session.metadata.get("outcome") if final_session.metadata else None)

                            profile_call_summary = ProfileCallSummary(
                                session_id=session_id,
                                summary_text=summary_text,
                                outcome=call_outcome,
                                transport_type=final_session.transport,
                                duration_seconds=duration_seconds,
                            )

                            session_data_for_ai: dict = {
                                "transcript": services.transcript_accumulator.to_dict(),
                                "summary": {"text": summary_text, "outcome": call_outcome},
                                "tool_usage": services.transcript_accumulator.get_tool_usage_summary(),
                            }

                            if services.metrics_logger and hasattr(services.metrics_logger, "_accumulator"):
                                session_data_for_ai["metrics"] = services.metrics_logger._accumulator.to_dict()

                            session_data_for_ai["transport_details"] = {
                                "transport": final_session.transport,
                                "duration_seconds": duration_seconds,
                                "state": final_session.state.value if final_session.state else None,
                                "provider_session_id": final_session.provider_session_id,
                            }

                            if final_session.participants:
                                session_data_for_ai["participant_data"] = {
                                    "participants": [p.model_dump(mode="json") for p in final_session.participants]
                                }

                            if final_session.metadata:
                                session_data_for_ai["session_context"] = final_session.metadata

                            if services.hangup_observer:
                                hangup_artifact = services.hangup_observer.get_hangup_artifact()
                                if hangup_artifact.content:
                                    session_data_for_ai["hangup"] = hangup_artifact.content

                            # IMPORTANT:
                            # - Do the DB update inline so it cannot be cancelled by teardown.
                            # - Run slower AI extraction as a detached post-call task that we do NOT cancel.
                            try:
                                profile_manager = CustomerProfileManager(db)
                                required_fields = getattr(
                                    getattr(agent.config, "customer_profile_config", None), "ai_required_fields", None
                                )
                                # If use_language_from_profile is disabled, also skip extracting language_preference
                                use_lang_from_profile = agent.config.customer_profile_config.use_language_from_profile
                                if not use_lang_from_profile and required_fields:
                                    required_fields = [f for f in required_fields if f != "language_preference"]
                                    logger.debug(f"📇 Excluded language_preference from AI extraction (use_language_from_profile=False)")

                                updated_profile = await profile_manager.record_call_completion(
                                    identifier=identifier,
                                    identifier_type=identifier_type,
                                    call_summary=profile_call_summary,
                                    customer_name=customer_name,
                                )
                                logger.info(f"📇 Customer profile updated for {identifier_type}={identifier}")

                                if updated_profile:
                                    # Auto-clear outbound DND after an inbound call completes.
                                    # This matches the desired behavior: if the customer called us,
                                    # we treat that as permission to call them again.
                                    if transport_name in ("plivo", "twilio") and actual_direction == "inbound":
                                        try:
                                            cleared = await profile_manager.clear_telephony_outbound_dnd(
                                                updated_profile.profile_id,
                                                session_id=session_id,
                                            )
                                            if cleared:
                                                logger.info(
                                                    f"📵 Cleared outbound DND after inbound call for profile {updated_profile.profile_id}"
                                                )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to auto-clear outbound DND for profile {updated_profile.profile_id}: {e}"
                                            )

                                    async def _extract_profile_ai_data(profile_id: str):
                                        try:
                                            await profile_manager.extract_and_update_ai_data(
                                                profile_id=profile_id,
                                                session_data=session_data_for_ai,
                                                call_outcome=call_outcome,
                                                ai_required_fields=required_fields,
                                                session_id=session_id,
                                            )
                                            # Enforce requested behavior:
                                            # For inbound calls, ALWAYS keep outbound DND cleared, even if AI extraction
                                            # detects an opt-out intent and sets it back to True.
                                            if transport_name in ("plivo", "twilio") and actual_direction == "inbound":
                                                try:
                                                    await profile_manager.clear_telephony_outbound_dnd(
                                                        profile_id,
                                                        session_id=session_id,
                                                        updated_by="system_auto_clear_post_ai",
                                                        reason="inbound_call_received_post_ai",
                                                    )
                                                    logger.info(
                                                        f"📵 Re-cleared outbound DND after AI extraction for inbound call (profile {profile_id})"
                                                    )
                                                except Exception as e:
                                                    logger.warning(
                                                        f"Failed to re-clear outbound DND after AI extraction for profile {profile_id}: {e}"
                                                    )
                                            logger.info(f"🤖 AI data extraction completed for profile {profile_id}")
                                        except Exception as profile_error:
                                            logger.warning(
                                                f"Failed AI extraction for customer profile {profile_id}: {profile_error}"
                                            )

                                    extraction_task = asyncio.create_task(
                                        _extract_profile_ai_data(updated_profile.profile_id)
                                    )
                                    post_call_tasks.add(extraction_task)

                                    def _discard_post_call_task(t: asyncio.Task) -> None:
                                        post_call_tasks.discard(t)
                                        try:
                                            exc = t.exception()
                                            if exc:
                                                logger.warning(
                                                    f"Post-call customer profile task failed: {type(exc).__name__}: {exc}"
                                                )
                                        except asyncio.CancelledError:
                                            pass
                                        except Exception:
                                            pass

                                    extraction_task.add_done_callback(_discard_post_call_task)
                            except Exception as profile_error:
                                logger.warning(f"Failed to record call to customer profile: {profile_error}")
            else:
                logger.info("🛑 Skipping customer profile update (customer_profile_config.update_after_call=False)")
        except Exception as profile_setup_error:
            logger.warning(f"Error setting up customer profile recording: {profile_setup_error}")

        # Post-call actions
        try:
            if agent and agent.config.context_config and agent.config.context_config.call_lifecycle and agent.config.context_config.call_lifecycle.post_call_enabled:
                from app.services.post_call_action_executor import execute_post_call_actions
                logger.debug("Executing post-call actions...")
                summary_messages = services.summarization_observer.messages
                call_summary = call_summary or await generate_summary(summary_messages, agent.config)
                
                # Extract hangup reason from hangup observer and add to session metadata
                if hasattr(services.hangup_observer, "get_hangup_artifact"):
                    hangup_artifact = services.hangup_observer.get_hangup_artifact()
                    if hangup_artifact and hasattr(hangup_artifact, "content"):
                        hangup_reason = hangup_artifact.content
                        if hangup_reason and final_session.metadata:
                            final_session.metadata["disconnection_reason"] = hangup_reason.get("disconnection_reason")
                            if "details" in hangup_reason:
                                final_session.metadata["hangup_details"] = hangup_reason["details"]
                elif hasattr(services.hangup_observer, "reason"):
                    # Fallback: construct from observer attributes
                    if final_session.metadata:
                        final_session.metadata["disconnection_reason"] = getattr(services.hangup_observer, "reason", "unknown")
                        final_session.metadata["hangup_details"] = getattr(services.hangup_observer, "details", {})
                
                await execute_post_call_actions(
                    session=final_session,
                    call_summary=call_summary,
                    call_lifecycle_config=agent.config.context_config.call_lifecycle,
                    enrichment_data=getattr(agent, "_enrichment_data", None),
                    customer_exists=getattr(agent, "_customer_exists", False),
                    db=db,
                    tenant_id=tenant_id,
                    aiohttp_session=aiohttp_session,
                )
        except Exception as e:
            logger.error(f"Error during post-call action execution: {e}", exc_info=True)

        logger.info("Pipeline cleanup complete.")
    finally:
        # Always cancel any background tasks created during the pipeline run.
        # If we don't, they can keep references alive and prevent proper shutdown.
        if background_tasks:
            logger.info(f"🧨 Cancelling {len(background_tasks)} background task(s) for session {session_id}")
            for t in list(background_tasks):
                try:
                    t.cancel()
                except Exception:
                    pass
            try:
                await asyncio.gather(*background_tasks, return_exceptions=True)
            except Exception:
                pass
            background_tasks.clear()

        # Post-call tasks (like customer profile AI extraction) are intentionally NOT cancelled.
        # They can continue running after the pipeline finishes.
        if post_call_tasks:
            logger.info(
                f"📌  Leaving {len(post_call_tasks)} post-call task(s) running for session {session_id} (not cancelled)"
            )

        # Ensure websocket services are properly cancelled before cleanup
        # This prevents dangling tasks even for normal pipeline completion (not just disconnect)
        logger.info(f"🛑 Ensuring websocket services are cancelled for session {session_id}")
        await shutdown_websocket_services([stt, llm, tts, context_aggregator, transcript_processor, audiobuffer], session_id)

        # Always cleanup services in a simple, predictable order.
        # By this point, EndFrame/CancelFrame have flowed through the pipeline and
        # each service has seen its stop/cancel signals; cleanup() here just lets
        # them release any remaining resources (e.g., websocket receive loops).
        try:
            logger.info(f"🧹 Starting service cleanup for session {session_id}")
            for service in [stt, llm, tts, context_aggregator, transcript_processor, audiobuffer]:
                if not service or not hasattr(service, "cleanup"):
                    continue
                try:
                    logger.debug(f"Cleaning up service {service}")
                    await service.cleanup()
                except Exception as e:
                    logger.warning(f"⚠️ Error during cleanup for {service}: {e}", exc_info=True)
            logger.info(f"✅ Service cleanup completed for session {session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error during service cleanup for session {session_id}: {e}", exc_info=True)

        # Always disconnect transport after services are cleaned up.
        # This is critical to prevent the session from hanging after hangup/tool termination or disconnect.
        try:
            if transport and hasattr(transport, "disconnect"):
                logger.info(f"🔌 Explicitly disconnecting transport for session {session_id}")
                await transport.disconnect()
                logger.info(f"✅ Transport disconnected for session {session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Error disconnecting transport for session {session_id}: {e}", exc_info=True)

        # Remove any per-session globals to avoid leaking references across calls.
        try:
            _artifact_managers.pop(session_id, None)
            _unregister_transcription_filter(session_id)
        except Exception:
            pass

        await aiohttp_session.close()
        logger.info(f"AIOHTTP session closed for {session_id}.")
