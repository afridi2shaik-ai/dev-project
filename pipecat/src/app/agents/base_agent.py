import asyncio
import time

import aiohttp
from loguru import logger
from typing import Any

from app.processors import MultiTTSRouter
from app.schemas.services.agent import AgentConfig, PipelineMode, CustomerDetails
from app.schemas.services.llm import GeminiLLMConfig, OpenAILLMConfig
from app.schemas.services.stt import DeepgramSTTConfig, GoogleSTTConfig, OpenAISTTConfig, CartesiaSTTConfig, ElevenLabsSTTConfig, SonioxSTTConfig
from app.schemas.services.tts import DynamicTTSConfig, ElevenLabsTTSConfig, OpenAITTSConfig, SarvamTTSConfig, CartisiaTTSConfig, TTSConfig, AzureTTSConfig
from app.services.customer_profile_service import CustomerProfileService
from app.services.llm import create_gemini_multimodal_llm_service, create_google_text_llm_service, create_llm_service_with_context
from app.services.stt import create_deepgram_stt_service, create_google_stt_service, create_openai_stt_service, create_cartisia_stt_service, create_elevenlabs_stt_service, create_soniox_stt_service
from app.services.tts import create_elevenlabs_tts_service, create_openai_tts_service, create_sarvam_tts_service, create_cartisia_tts_service, create_azure_tts_service


class BaseAgent:    
    def __init__(self, agent_config: AgentConfig | None = None):
        self.config = agent_config or AgentConfig()  # type: ignore # All fields have defaults
        self.customer_details = self.config.customer_details

        self._stt = self._create_stt() if self.config.pipeline_mode in (PipelineMode.TRADITIONAL, PipelineMode.AUDIO_CHAT) else None
        self._llm = None
        self._tts = None
        self._context_aggregator = None
        self._messages: list[dict[str, str]] | None = None
        self._session_context = None  # Store session context
        self._customer_profile = None  # Store resolved customer profile
        self._voicemail_detector = None  # VoicemailDetector instance
        # For call lifecycle management
        self._enrichment_data: dict | None = None
        self._enrichment_success: bool = False
        self._customer_exists: bool = False
        self._enrichment_task = None

        # Pre-request cache for business tools (session-scoped)
        self._pre_request_cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._cache_lock = asyncio.Lock()

    def _create_tts_service_from_config(self, config: TTSConfig, aiohttp_session: aiohttp.ClientSession):
        """Helper method to create a single TTS service from a config."""
        if isinstance(config, SarvamTTSConfig):
            return create_sarvam_tts_service(voice_id=config.voice_id, model=config.model, sample_rate=config.sample_rate, params=config.params)
        elif isinstance(config, ElevenLabsTTSConfig):
            return create_elevenlabs_tts_service(voice_id=config.voice_id, model_id=config.model_id, voice_settings=config.voice_settings)
        elif isinstance(config, OpenAITTSConfig):
            return create_openai_tts_service(model=config.model, voice=config.voice, instructions=config.instructions, sample_rate=config.sample_rate)
        elif isinstance(config, CartisiaTTSConfig):
            return create_cartisia_tts_service(voice_id=config.voice_id, model=config.model, language=config.language, volume=config.volume, speed=config.speed, emotion=config.emotion)
        elif isinstance(config, AzureTTSConfig):
            return create_azure_tts_service(voice=config.voice, sample_rate=config.sample_rate, params=config.params)
        
        else:
            raise ValueError(f"Unsupported TTS provider for dynamic routing: {getattr(config, 'provider', 'Unknown')}")

    def _create_stt(self):
        if isinstance(self.config.stt, GoogleSTTConfig):
            return create_google_stt_service(
                language=self.config.stt.language,
                alternative_language_codes=self.config.stt.alternative_language_codes,
                model=self.config.stt.model,
                enable_automatic_language_detection=self.config.stt.enable_automatic_language_detection,
            )
        elif isinstance(self.config.stt, OpenAISTTConfig):
            return create_openai_stt_service(model=self.config.stt.model, language=self.config.stt.language, prompt=self.config.stt.prompt)
        elif isinstance(self.config.stt, DeepgramSTTConfig):
            return create_deepgram_stt_service(
                url=self.config.stt.url,
                base_url=self.config.stt.base_url,
                sample_rate=self.config.stt.sample_rate,
                live_options=self.config.stt.live_options,
                addons=self.config.stt.addons,
            )
        elif isinstance(self.config.stt, CartesiaSTTConfig):
            return create_cartisia_stt_service(
            base_url=self.config.stt.base_url,
            sample_rate=self.config.stt.sample_rate,
            live_options=self.config.stt.live_options,
          
          )
        elif isinstance(self.config.stt, ElevenLabsSTTConfig):
            return None
        elif isinstance(self.config.stt, SonioxSTTConfig):
            return create_soniox_stt_service(
                model=self.config.stt.model,
                language=self.config.stt.language,
                language_hints_strict=self.config.stt.language_hints_strict,
              
            )
        else:
            raise ValueError(f"Unsupported STT provider: {self.config.stt.provider}")

    async def _create_tts(self, aiohttp_session: aiohttp.ClientSession):
        if isinstance(self.config.tts, DynamicTTSConfig):
            # Create multiple TTS services for different languages
            tts_services = {}
            for lang_code, tts_config in self.config.tts.configs.items():
                tts_services[lang_code] = self._create_tts_service_from_config(tts_config, aiohttp_session)

            # Import the enhanced language detection service
            from app.services.language_detection_service import get_language_detection_service

            # Create the MultiTTSRouter with the language detection service
            language_service = get_language_detection_service(default_language=self.config.tts.default_language, confidence_threshold=0.7)

            self._tts = MultiTTSRouter(tts_services=tts_services, default_language=self.config.tts.default_language, language_detection_service=language_service)
        elif isinstance(self.config.tts, SarvamTTSConfig):
            self._tts = create_sarvam_tts_service(voice_id=self.config.tts.voice_id, model=self.config.tts.model, sample_rate=self.config.tts.sample_rate, params=self.config.tts.params)
        elif isinstance(self.config.tts, ElevenLabsTTSConfig):
            self._tts = create_elevenlabs_tts_service(voice_id=self.config.tts.voice_id, model_id=self.config.tts.model_id, voice_settings=self.config.tts.voice_settings)
        elif isinstance(self.config.tts, OpenAITTSConfig):
            self._tts = create_openai_tts_service(model=self.config.tts.model, voice=self.config.tts.voice, instructions=self.config.tts.instructions, sample_rate=self.config.tts.sample_rate)
        elif isinstance(self.config.tts, CartisiaTTSConfig):
            self._tts = create_cartisia_tts_service(voice_id=self.config.tts.voice_id ,model=self.config.tts.model,language=self.config.tts.language)
        elif isinstance(self.config.tts, AzureTTSConfig):
            self._tts = create_azure_tts_service(voice=self.config.tts.voice, sample_rate=self.config.tts.sample_rate, params=self.config.tts.params)
        else:
            raise ValueError(f"Unsupported TTS provider: {self.config.tts.provider}")

    async def _create_llm_and_context(self):
        if isinstance(self.config.llm, OpenAILLMConfig):
            system_prompt = self.config.llm.system_prompt_template
            if self.customer_details:
                if self.customer_details.name:
                    system_prompt += f" The user's name is {self.customer_details.name}."
                if self.customer_details.history:
                    system_prompt += f" Here is a summary of the last call with the user: {self.customer_details.history}"

            # Enhance system prompt with session context if available and enabled
            use_profile_prompt = getattr(getattr(self.config, "customer_profile_config", None), "use_in_prompt", False)

            if hasattr(self, "_session_context") and self._session_context and self.config.context_config.enhance_system_prompt:
                from app.services.session_context_service import SessionContextService

                context_service = SessionContextService(getattr(self, "_db", None), getattr(self, "_tenant_id", None))
                profile_for_prompt = self._customer_profile if use_profile_prompt else None
                # Determine if language preference should be included in the profile context
                include_lang_pref = self.config.customer_profile_config.use_language_from_profile
                context_info = context_service.format_system_prompt_context(
                    self._session_context,
                    customer_profile=profile_for_prompt,
                    include_language_preference=include_lang_pref
                )
                system_prompt = f"{system_prompt}\n\n{context_info}"
                logger.info("🎯 Enhanced system prompt with session context%s", " + customer profile" if profile_for_prompt else "")

            self._messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
            ]
            logger.debug(f"System prompt: {system_prompt}")

            self._llm, self._context_aggregator, self._messages = await create_llm_service_with_context(
                messages=self._messages,
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
                top_p=self.config.llm.top_p,
                max_tokens=self.config.llm.max_tokens,
                presence_penalty=self.config.llm.presence_penalty,
                frequency_penalty=self.config.llm.frequency_penalty,
                tools_config=self.config.tools,
                agent_config=self.config,
                aiohttp_session=getattr(self, "_aiohttp_session", None),
                db=getattr(self, "_db", None),
                tenant_id=getattr(self, "_tenant_id", None),
                agent=self,
            )

        elif isinstance(self.config.llm, GeminiLLMConfig):
            system_prompt = "You are a friendly AI assistant."  # A default, as Gemini handles prompts differently.
            self._messages = [{"role": "system", "content": system_prompt}]

            if self.config.pipeline_mode == PipelineMode.MULTIMODAL:
                self._llm, self._context_aggregator, self._messages = await create_gemini_multimodal_llm_service(
                    messages=self._messages,
                    model=self.config.llm.model,
                    voice_id=self.config.llm.voice_id,
                    temperature=self.config.llm.temperature,
                    tools_config=self.config.tools,
                    agent_config=self.config,
                    aiohttp_session=getattr(self, "_aiohttp_session", None),
                    db=getattr(self, "_db", None),
                    tenant_id=getattr(self, "_tenant_id", None),
                    agent=self,
                )
            else:  # Traditional pipeline
                # Add customer profile context for multimodal traditional Gemini path
                use_profile_prompt = getattr(getattr(self.config, "customer_profile_config", None), "use_in_prompt", False)
                if self._customer_profile and use_profile_prompt:
                    try:
                        include_lang_pref = self.config.customer_profile_config.use_language_from_profile
                        profile_context = CustomerProfileService(getattr(self, "_db", None), getattr(self, "_tenant_id", None)).build_profile_context(
                            self._customer_profile,
                            include_language_preference=include_lang_pref
                        )
                        system_prompt = f"{system_prompt}\n\n{profile_context}"
                        self._messages = [{"role": "system", "content": system_prompt}]
                        logger.info("🎯 Enhanced system prompt with customer profile context (Gemini)")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to add customer profile context to Gemini prompt: {e}")

                self._llm, self._context_aggregator, self._messages = await create_google_text_llm_service(
                    messages=self._messages,
                    model=self.config.llm.model,
                    temperature=self.config.llm.temperature,
                    tools_config=self.config.tools,
                    agent_config=self.config,
                    aiohttp_session=getattr(self, "_aiohttp_session", None),
                    db=getattr(self, "_db", None),
                    tenant_id=getattr(self, "_tenant_id", None),
                    agent=self,
                )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.llm.provider}")

        # Tools are registered and advertised inside the LLM service factory

    async def set_session_context(self, session_id: str, transport_name: str, db, tenant_id: str, provider_session_id: str | None = None, user_details: dict | None = None, transport_metadata: dict | None = None, call_data: dict | None = None):
        """Build and set session context for AI awareness."""
        try:
            # Check if context building is enabled
            if not self.config.context_config.enabled:
                logger.info(f"🎯 Session context disabled for {session_id} via context_config")
                self._session_context = None
                return

            from app.services.session_context_service import SessionContextService
            from app.tools.session_context_tool import set_session_context

            context_service = SessionContextService(db, tenant_id)

            context = await context_service.build_session_context(
                session_id=session_id,
                transport_name=transport_name,
                provider_session_id=provider_session_id,
                user_details=user_details,
                transport_metadata=transport_metadata,
                call_data=call_data,
                context_config=self.config.context_config
            )

            # Set for tool access (global storage)
            set_session_context(context)

            # Store in agent
            self._session_context = context
            logger.debug(f"🎯 Session context stored: user_phone={getattr(context.user, 'phone_number', None)}, transport_user_phone={getattr(context.transport, 'user_phone_number', None)}")

            # Resolve and store customer profile for prompt personalization
            try:
                user_phone = getattr(context.transport, "user_phone_number", None)
                user_email = getattr(context.user, "email", None)
                profile_service = CustomerProfileService(db, tenant_id)
                resolved_profile = await profile_service.resolve_profile_for_session(
                    transport_type=transport_name,
                    user_phone=user_phone,
                    user_email=user_email,
                )

                if resolved_profile:
                    self._customer_profile = resolved_profile
                    logger.info(
                        "🎯 Resolved returning customer profile: %s (%s)",
                        self._customer_profile.profile_id,
                        self._customer_profile.name or "unnamed",
                    )
                    # Apply customer details for personalization if missing
                    if not self.customer_details:
                        self.customer_details = CustomerDetails(
                            name=self._customer_profile.name,
                            email=self._customer_profile.email,
                        )
                        self.config.customer_details = self.customer_details
                    else:
                        if not self.customer_details.name and self._customer_profile.name:
                            self.customer_details.name = self._customer_profile.name
                        if not self.customer_details.email and getattr(self._customer_profile, "email", None):
                            self.customer_details.email = self._customer_profile.email
                elif self._customer_profile:
                    # Keep previously resolved profile instead of clearing it when a later lookup fails
                    logger.debug(
                        "🔄 No new customer profile resolved for session %s; retaining previously resolved profile %s",
                        session_id,
                        self._customer_profile.profile_id,
                    )
                else:
                    logger.debug("🔍 No customer profile resolved for session %s (transport=%s)", session_id, transport_name)
            except Exception as profile_err:
                logger.warning(f"⚠️ Unable to resolve customer profile for session {session_id}: {profile_err}")

            # Update session document with context summary
            from app.managers.session_manager import SessionManager

            session_manager = SessionManager(db)
            context_summary = {
                "transport_mode": context.transport.mode,
                "has_user_details": bool(context.user.name or context.user.email),
                "has_phone_numbers": bool(context.transport.user_phone_number),
                "call_direction": context.transport.call_direction,
                "context_enabled": self.config.context_config.enabled,
                "user_phone_number": context.transport.user_phone_number if self.config.context_config.include_phone_numbers else None,
                "agent_phone_number": context.transport.agent_phone_number if self.config.context_config.include_phone_numbers else None,
                "customer_profile_id": getattr(self._customer_profile, "profile_id", None) if self._customer_profile else None,
            }
            await session_manager.update_session_context_summary(session_id, context_summary)

            logger.info(f"🎯 Session context built and stored for {session_id}")

        except Exception as e:
            logger.error(f"Error setting session context for {session_id}: {e}", exc_info=True)
            self._session_context = None

    async def _create_voicemail_detector(self):
        """Create VoicemailDetector if enabled in config."""
        if not self.config.voicemail_detector.enabled:
            return

        if self.config.pipeline_mode != PipelineMode.TRADITIONAL:
            logger.warning("VoicemailDetector only works with TRADITIONAL pipeline mode")
            return

        from pipecat.extensions.voicemail.voicemail_detector import VoicemailDetector
        from app.core.config import settings

        # Create classifier LLM - use a more reliable model for classification than the conversation model
        # For better accuracy, prefer GPT-4 over GPT-4.1-nano or other lightweight models
        classifier_llm = None
        classifier_model = self._get_optimal_classifier_model()

        if isinstance(self.config.llm, OpenAILLMConfig):
            from pipecat.services.openai.llm import OpenAILLMService

            classifier_llm = OpenAILLMService(
                api_key=settings.OPENAI_API_KEY,
                model=classifier_model,
            )
        elif isinstance(self.config.llm, GeminiLLMConfig):
            from pipecat.services.google.llm import GoogleLLMService

            classifier_llm = GoogleLLMService(
                api_key=settings.GEMINI_API_KEY,
                model=classifier_model,
            )
        else:
            logger.warning(f"VoicemailDetector: Unsupported LLM provider {self.config.llm.provider}")
            return

        # Create custom prompt optimized for conversation-first classification
        custom_prompt = self._create_custom_voicemail_prompt()

        # Create STT-aware voicemail detector that properly handles streaming data
        self._voicemail_detector = self._create_stt_aware_voicemail_detector(
            classifier_llm, custom_prompt, self.config.voicemail_detector.voicemail_response_delay
        )

        logger.info(f"VoicemailDetector created with provider={self.config.llm.provider}, model={classifier_model}")
        logger.info(f"VoicemailDetector: Enhanced STT handling - 2.0s aggregation timeout captures complete utterances")
        logger.info(f"VoicemailDetector: Streaming tokens ('this'+'is'+'ajay') aggregated into 'this is ajay' before classification")
        logger.info(f"VoicemailDetector: Using definitive classification (no fallback) with {len(custom_prompt)} char prompt")
        logger.debug(f"VoicemailDetector prompt preview: {custom_prompt[:200]}...")

    def _get_optimal_classifier_model(self) -> str:
        """Get the optimal LLM model for voicemail classification.

        Uses GPT-4 for best accuracy and consistency.
        """
        if isinstance(self.config.llm, OpenAILLMConfig):
            # Always use GPT-4 for voicemail classification - most reliable and consistent
            logger.info(f"🎯 Using GPT-4 for voicemail classification (best model for accuracy)")
            return "gpt-4"

        elif isinstance(self.config.llm, GeminiLLMConfig):
            # For Gemini, use the most capable model available
            return "gemini-1.5-pro"

        # Default fallback
        return self.config.llm.model

    def _create_stt_aware_voicemail_detector(self, classifier_llm, custom_prompt, response_delay):
        """Create a voicemail detector that properly handles streaming STT data.

        The standard VoicemailDetector expects LLM responses, but we need one that:
        1. Receives streaming STT transcription frames ("this", "is", "ajay")
        2. Aggregates complete utterances with longer timeouts to ensure "this is ajay" is captured as one unit
        3. Sends complete utterances to classification LLM
        4. Processes LLM responses definitively
        
        CRITICAL FIX: We also patch the user aggregator to ignore LLMRunFrame to prevent
        the classifier from being triggered without actual user transcription. When the main
        conversation LLM sends its first message via LLMRunFrame, this frame flows through
        the voicemail detector's parallel pipeline. Without this fix, the classifier LLM
        would be triggered with just the system prompt (no user content), causing it to
        hallucinate fictional voicemail text and incorrectly classify real conversations.
        """
        from pipecat.extensions.voicemail.voicemail_detector import VoicemailDetector
        from pipecat.frames.frames import LLMRunFrame

        # Create the VoicemailDetector with custom prompt
        detector = VoicemailDetector(
            llm=classifier_llm,
            voicemail_response_delay=response_delay,
            custom_system_prompt=custom_prompt,
        )

        # CRITICAL FIX: Patch the user aggregator to ignore LLMRunFrame
        # The VoicemailDetector's parallel pipeline has a classification branch with a user aggregator.
        # When LLMRunFrame flows through, the aggregator's _handle_llm_run() pushes LLMContextFrame
        # with just the system prompt (no user content). This triggers the classifier LLM which
        # then hallucinates fictional voicemail text and incorrectly classifies real conversations.
        #
        # By patching _handle_llm_run to do nothing, we ensure the classifier only runs when
        # actual user transcription arrives through _handle_transcription().
        user_aggregator = detector._context_aggregator.user()
        
        async def patched_handle_llm_run(frame: LLMRunFrame):
            """Patched handler that ignores LLMRunFrame to prevent premature classification.
            
            The standard implementation would push LLMContextFrame here, triggering the classifier
            with just the system prompt. We skip this entirely and only classify actual transcriptions.
            """
            logger.debug(f"VoicemailDetector: Ignoring LLMRunFrame (waiting for actual user transcription)")
            # Do nothing - don't push context frame, preventing premature classification
            pass
        
        user_aggregator._handle_llm_run = patched_handle_llm_run
        logger.info("Patched VoicemailDetector user aggregator to ignore LLMRunFrame (prevents premature classification)")

        logger.info("VoicemailDetector configured for STT streaming with 2.0s aggregation timeout")
        logger.info("Will aggregate streaming tokens ('this'+'is'+'ajay') into complete utterances before classification")
        return detector

    def _create_custom_context_aggregator(self, system_prompt, user_params):
        """Create a custom context aggregator with enhanced STT handling for voicemail detection.
        
        NOTE: This method is no longer used as the LLMRunFrame fix is now applied via
        monkey-patching in _create_stt_aware_voicemail_detector(). Keeping this method
        for potential future use or alternative approaches.
        """
        from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
        from pipecat.processors.aggregators.llm_context import LLMContext

        messages = [{"role": "system", "content": system_prompt}]
        context = LLMContext(messages)
        return LLMContextAggregatorPair(context, user_params=user_params)

    def _create_custom_voicemail_prompt(self) -> str:
        """Create a definitive prompt for voicemail classification.

        This prompt provides clear, binary classification with specific examples.
        Once classified as voicemail, it's treated as definitive - no fallback.
        """
        return """You are a voicemail detection classifier for an OUTBOUND calling system. A bot has called a phone number and you need to determine if a human answered or if the call went to voicemail based on the provided text.

CRITICAL: Your classification is FINAL and DEFINITIVE. Once you classify as VOICEMAIL, the call will be treated as voicemail with no fallback to conversation.

HUMAN ANSWERED - LIVE CONVERSATION (respond "CONVERSATION"):
- Direct greetings: "Hello", "Hi", "Hello?", "Hi there"
- Personal identification: "Speaking", "This is John", "Yes, that's me"
- Interactive questions: "Who is this?", "What can I help you with?"
- Conversational responses: "Sure", "Okay", "Yes please", "Go ahead"
- Brief acknowledgments: "Yep", "Uh huh", "Okay", "Yes", "No"
- Professional responses: "Good morning", "How may I help you?"
- Any response that indicates live human interaction

VOICEMAIL SYSTEM (respond "VOICEMAIL") - DEFINITIVE CLASSIFICATION:
- Automated greetings: "You've reached voicemail", "Please leave a message"
- Carrier messages: "The number you have dialed is not in service"
- Automated instructions: "Press 1 to leave a message", "Mailbox is full"
- Professional voicemail: "I'm not available right now, please leave a message"
- Formal messaging instructions: "leave your name and number", "I'll call you back"
- Any clearly automated or pre-recorded message

CLASSIFICATION RULES:
1. If it sounds like a real person: CONVERSATION
2. If it sounds automated or pre-recorded: VOICEMAIL
3. Short responses ("Hello", "Yes", "Speaking") are CONVERSATION
4. Long formal messages about leaving messages are VOICEMAIL
5. When in doubt, classify as CONVERSATION (but be decisive)

"""
        + "Respond with ONLY \"CONVERSATION\" or \"VOICEMAIL\" (no other text)."

    async def get_services(self, aiohttp_session: aiohttp.ClientSession, db=None, tenant_id=None):
        # Store aiohttp session for custom API tool access and database info
        self._aiohttp_session = aiohttp_session
        self._db = db
        self._tenant_id = tenant_id
        if self._stt is None and isinstance(self.config.stt, ElevenLabsSTTConfig):
            self._stt = create_elevenlabs_stt_service(
            aiohttp_session=aiohttp_session,
            language=self.config.stt.language,
            model=self.config.stt.model
        )
        
        await self._create_llm_and_context()
        if self.config.pipeline_mode == PipelineMode.TRADITIONAL:
            await self._create_tts(aiohttp_session)
        
        await self._create_voicemail_detector()

        # Trigger pre-call enrichment now that all services/sessions are initialized
        if self.config.context_config.call_lifecycle and self.config.context_config.call_lifecycle.pre_call_enrichment_enabled and self.config.context_config.call_lifecycle.pre_call_enrichment_tool_id:
            from app.services.crm_context_enricher import enrich_context_from_crm

            if self._session_context:
                logger.debug(f"🎯 Starting CRM enrichment with session context: {self._session_context}")
                self._enrichment_task = asyncio.create_task(
                    enrich_context_from_crm(
                        session_context=self._session_context,
                        context_aggregator=getattr(self, "_context_aggregator", None),
                        tool_id=self.config.context_config.call_lifecycle.pre_call_enrichment_tool_id,
                        db=self._db,
                        tenant_id=self._tenant_id,
                        aiohttp_session=self._aiohttp_session,
                        agent=self,
                    )
                )
            else:
                logger.warning("🎯 Session context not available for CRM enrichment")
        return self._stt, self._llm, self._tts, self._context_aggregator, self._messages

    def get_cached_pre_request(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached pre-request result if it exists.
        
        Args:
            cache_key: Cache key to look up
        
        Returns:
            Cached data if found, None otherwise
        """
        if cache_key not in self._pre_request_cache:
            return None

        cached_data, cached_time = self._pre_request_cache[cache_key]
        logger.debug(f"✅ Pre-request cache HIT for key: {cache_key} (cached {time.time() - cached_time:.1f}s ago)")
        return cached_data

    async def set_cached_pre_request(self, cache_key: str, data: dict[str, Any]) -> None:
        """Store pre-request result in session cache.
        
        Args:
            cache_key: Cache key to store under
            data: Data to cache
        """
        async with self._cache_lock:
            self._pre_request_cache[cache_key] = (data, time.time())
            logger.debug(f"💾 Pre-request cache SET for key: {cache_key} (fields: {list(data.keys())})")

    def clear_pre_request_cache(self, cache_key: str | None = None) -> None:
        """Clear specific cache key or all cache.
        
        Args:
            cache_key: Specific key to clear. If None, clears all cache.
        """
        if cache_key:
            if cache_key in self._pre_request_cache:
                del self._pre_request_cache[cache_key]
                logger.debug(f"🗑️ Pre-request cache CLEARED for key: {cache_key}")
        else:
            cache_size = len(self._pre_request_cache)
            self._pre_request_cache.clear()
            logger.debug(f"🗑️ Pre-request cache CLEARED (all {cache_size} keys)")
