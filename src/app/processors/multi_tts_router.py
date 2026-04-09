from __future__ import annotations

import re

from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    StartFrame,
    TTSSpeakFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.ai_service import AIService

from app.services.language_detection_service import LanguageDetectionService, get_language_detection_service


class MultiTTSRouter(FrameProcessor):
    """A simplified TTS router that detects language once per response and sticks with it.
    This avoids the complexity of mid-response switching that was causing issues.
    """

    def __init__(
        self,
        tts_services: dict[str, AIService],
        default_language: str = "en",
        confidence_threshold: float = 0.7,
        language_detection_service: LanguageDetectionService | None = None,
    ):
        super().__init__()
        self.tts_services = tts_services
        self.default_language = default_language
        self.current_service = None
        self.last_used_service = default_language  # Remember last used service for idle messages
        self.confidence_threshold = confidence_threshold
        self.accumulated_text = ""
        self.response_in_progress = False

        # Use provided language detection service or get the global shared one
        self.language_service = language_detection_service or get_language_detection_service(default_language=default_language, confidence_threshold=confidence_threshold)

        # Subscribe to language changes to track current language
        self.language_service.subscribe_to_language_changes(self._on_language_change)

        logger.debug(f"MultiTTSRouter initialized with services: {list(tts_services.keys())}")

    def _on_language_change(self, new_language: str):
        """Handle language change notifications from the detection service."""
        logger.debug(f"MultiTTSRouter language changed to: {new_language}")

    def _is_valid_text_for_tts(self, text: str) -> bool:
        """Validate text before sending to TTS services to prevent Sarvam errors.

        This prevents the error: "Text must contain at least one character from the allowed languages"
        """
        if not text:
            return False

        # Remove whitespace for analysis
        cleaned_text = text.strip()

        # Check minimum length (at least 1 meaningful character)
        if len(cleaned_text) == 0:
            return False

        # Check if text contains only punctuation and whitespace
        if re.match(r"^[.,!?\s]*$", cleaned_text):
            return False

        # Check if text is only filler sounds
        if re.match(r"^(uh|um|ah|er|hmm)\s*$", cleaned_text, re.IGNORECASE):
            return False

        return True

    def detect_language(self, text: str) -> str:
        """Detect language from text and return service key based on configured services."""
        # First validate text to prevent TTS errors
        if not self._is_valid_text_for_tts(text):
            logger.warning(f"Invalid text for TTS detected: '{text}' - using default language")
            return self.default_language

        # Use the shared language detection service
        detected_lang = self.language_service.detect_language(text, update_current=True)

        # Check if we have a TTS service configured for this detected language
        if detected_lang in self.tts_services:
            return detected_lang
        else:
            # No service configured for detected language, use default
            logger.debug(f"No TTS service configured for detected language '{detected_lang}', using default '{self.default_language}'")
            return self.default_language

    def _override_child_queue_frame(self, service):
        """Override a child service's queue_frame to redirect ALL frames through the router.

        TTS services are child services of MultiTTSRouter, not directly linked in the pipeline.
        When they generate audio frames or other outputs, those frames must flow through
        the MultiTTSRouter so it can push them downstream to the next processor.
        """
        # Store reference to the router's push_frame method
        router_push_frame = self.push_frame

        async def redirecting_queue_frame(frame, direction):
            frame_type = type(frame).__name__

            # Redirect TTSSpeakFrame back to router for re-routing
            if hasattr(frame, "text") and "TTSSpeakFrame" in frame_type:
                logger.debug(f"🔄 Redirecting {frame_type} from {type(service).__name__} back to MultiTTSRouter")
                await self.queue_frame(frame, direction)
            else:
                # ✅ CRITICAL FIX: ALL other frames from TTS services (especially audio frames)
                # must be pushed through the router to reach the next processor in the pipeline
                # logger.debug(f"📤 TTS service generated {frame_type}, pushing through router downstream")
                await router_push_frame(frame, direction)

        # Replace the service's queue_frame method
        service.queue_frame = redirecting_queue_frame

    async def setup(self, setup):
        """Set up this processor and all child TTS services."""
        await super().setup(setup)
        for service in self.tts_services.values():
            await service.setup(setup)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames by routing to appropriate TTS service."""

        # ✅ CRITICAL: Control frames MUST be processed by parent class first
        # StartFrame initializes processor's internal queue (_FrameProcessor__input_queue)
        # Without this, the processor cannot function
        if isinstance(frame, (StartFrame, EndFrame, CancelFrame, TTSUpdateSettingsFrame)):
            logger.debug(f"⚙️ Control frame: {type(frame).__name__} - passing to super() and all TTS services")
            # First, let parent initialize
            await super().process_frame(frame, direction)
            # Then forward to all TTS services
            for service in self.tts_services.values():
                await service.process_frame(frame, direction)
            return

        # ✅ CRITICAL: Context frames must pass through to reach the LLM
        # These frames should NOT be routed to TTS services - just pass them through
        frame_type = type(frame).__name__
        bypass_keywords = ["Context", "LLMContext", "OpenAILLM", "FunctionCall", "FunctionResult"]
        should_bypass = any(keyword in frame_type for keyword in bypass_keywords)

        if should_bypass:
            logger.info(f"⏭️ Context frame bypassing TTS router: {frame_type} (direction={direction.name})")
            # CRITICAL: Must call push_frame() to actually pass the frame to the next processor!
            # super().process_frame() only notifies observers, it doesn't push frames
            await self.push_frame(frame, direction)
            return

        # Log important TTS-related frames for debugging
        if isinstance(frame, (TTSSpeakFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame)):
            logger.info(f"📥 MultiTTSRouter received {type(frame).__name__}: {getattr(frame, 'text', 'N/A')}")

        # Handle TTSSpeakFrame (idle messages, hangup messages, business tool engaging words)
        # CRITICAL FIX: Process these frames but also let audio flow downstream
        if isinstance(frame, TTSSpeakFrame):
            logger.info(f"🎯 MultiTTSRouter processing TTSSpeakFrame: '{frame.text}'")

            # 🛡️ CRITICAL FIX: Validate text before sending to TTS to prevent Sarvam errors
            if not self._is_valid_text_for_tts(frame.text):
                logger.warning(f"🛡️ Blocking invalid TTSSpeakFrame text from TTS: '{frame.text}'")
                return  # Block invalid text from reaching TTS services

            # Detect language for the TTSSpeakFrame text
            detected_service = self.detect_language(frame.text)
            logger.info(f"🎯 TTSSpeakFrame language detected: '{detected_service}' for text: '{frame.text}'")

            # Select appropriate service
            if detected_service in self.tts_services:
                tts_service = self.tts_services[detected_service]
                logger.info(f"🎯 Processing TTSSpeakFrame with {detected_service} TTS service")
            else:
                # Fallback to default service
                logger.info(f"🎯 No service for detected language '{detected_service}', using default")
                tts_service = self.tts_services[self.default_language]

            # FIX: Process frame through TTS service (this generates audio frames)
            # The TTS service will push audio frames downstream through its own pipeline link
            try:
                await tts_service.process_frame(frame, FrameDirection.DOWNSTREAM)
                logger.debug(f"✅ TTSSpeakFrame processed successfully by {detected_service} service")
            except Exception as e:
                logger.error(f"❌ Error processing TTSSpeakFrame: {e}", exc_info=True)
                # On error, try to push the original frame downstream as fallback
                await self.push_frame(frame, direction)

            return  # Don't process further - audio frames are already being generated

        # Start of LLM response - detect language and choose service
        if isinstance(frame, LLMFullResponseStartFrame):
            logger.info(f"🎬 LLM Response START - Resetting state (prev service: {self.current_service})")
            self.accumulated_text = ""  # Reset
            self.response_in_progress = True
            self.current_service = None  # Reset current service for new response
            # Don't choose service yet, wait for some text
            return  # Don't push this frame, we'll send it to selected service

        # Accumulate text and detect language once we have enough
        elif isinstance(frame, LLMTextFrame) and self.response_in_progress:
            text_preview = frame.text[:50] if frame.text and len(frame.text) > 50 else (frame.text or "")
            logger.debug(f"📝 LLM Text received: '{text_preview}' (response_in_progress={self.response_in_progress})")
            text_content = frame.text

            # ✅ FIX: Always accumulate ALL tokens INCLUDING punctuation
            # OpenAI streams punctuation as separate tokens (e.g., ',' or '...')
            # We must NOT filter these during streaming - punctuation is essential for TTS pacing
            # Only skip truly empty/None tokens - validation happens on complete text later
            if text_content is None or text_content == "":
                logger.debug(f"🛡️ Skipping empty LLMTextFrame")
                return  # Only skip truly empty tokens

            self.accumulated_text += text_content

            # If we don't have a service yet and have enough text, detect language
            if not self.current_service and len(self.accumulated_text.strip()) >= 20:
                detected_service = self.detect_language(self.accumulated_text)
                logger.info(f"Selected TTS service: {detected_service} for response")
                self.current_service = detected_service

                # Send start frame to the selected service
                if self.current_service in self.tts_services:
                    tts_service = self.tts_services[self.current_service]
                    await tts_service.process_frame(LLMFullResponseStartFrame(), direction)

                    # Send all accumulated text to the selected service
                    # Create a new LLMTextFrame with all the accumulated text
                    accumulated_frame = LLMTextFrame(text=self.accumulated_text)
                    await tts_service.process_frame(accumulated_frame, direction)

            # Only route new text if we already have a selected service
            elif self.current_service and self.current_service in self.tts_services:
                tts_service = self.tts_services[self.current_service]
                await tts_service.process_frame(frame, direction)

            # FIX: If no service is selected yet, just accumulate (don't lose frames)
            # The service will be selected when we have enough text or at response end
            return  # Don't push downstream, we're routing to TTS service

        # CRITICAL FIX: Handle LLMTextFrame when response_in_progress is False
        # This can happen if LLMFullResponseStartFrame was missed or after tool execution
        elif isinstance(frame, LLMTextFrame) and not self.response_in_progress:
            text_preview = frame.text[:50] if frame.text and len(frame.text) > 50 else (frame.text or "None")
            logger.warning(f"⚠️ LLMTextFrame received but response_in_progress=False! Text: '{text_preview}'")

            # ✅ FIX: Only skip truly empty tokens, allow punctuation to accumulate
            if frame.text is None or frame.text == "":
                logger.warning(f"🛡️ Blocking empty emergency LLMTextFrame")
                return  # Block truly empty text only

            logger.warning("⚠️ Auto-recovering: Starting new response sequence")

            # Auto-start a response sequence
            self.accumulated_text = frame.text
            self.response_in_progress = True
            self.current_service = None

            # Detect language immediately since we have text
            detected_service = self.detect_language(self.accumulated_text)
            logger.info(f"🔧 Emergency language detection: {detected_service}")
            self.current_service = detected_service

            # Send to appropriate service
            if self.current_service in self.tts_services:
                tts_service = self.tts_services[self.current_service]
                await tts_service.process_frame(LLMFullResponseStartFrame(), direction)
                await tts_service.process_frame(frame, direction)
                logger.info(f"✅ Auto-recovered LLMTextFrame routed to {self.current_service}")
            return

        # End of LLM response - finalize
        elif isinstance(frame, LLMFullResponseEndFrame):
            logger.info(f"🏁 LLM Response END - Service: {self.current_service}, Accumulated: {len(self.accumulated_text)} chars")
            logger.debug(f"LLM response ended, used service: {self.current_service}, accumulated: '{self.accumulated_text}'")
            self.response_in_progress = False

            # FIX: Handle short responses (<20 chars) that never triggered service selection
            if not self.current_service and self.accumulated_text.strip():
                # 🛡️ CRITICAL FIX: Validate accumulated text before processing short responses
                if not self._is_valid_text_for_tts(self.accumulated_text):
                    logger.warning(f"🛡️ Blocking invalid short response from TTS: '{self.accumulated_text}'")
                    # Reset state and don't send to TTS
                    self.current_service = None
                    self.accumulated_text = ""
                    return

                # We have text but never selected a service (text was too short)
                logger.info(f"Short response detected ({len(self.accumulated_text)} chars), detecting language now")
                detected_service = self.detect_language(self.accumulated_text)
                self.current_service = detected_service

                # Send the complete response to the selected service
                if self.current_service in self.tts_services:
                    tts_service = self.tts_services[self.current_service]
                    # Send start, text, and end frames
                    await tts_service.process_frame(LLMFullResponseStartFrame(), direction)
                    accumulated_frame = LLMTextFrame(text=self.accumulated_text)
                    await tts_service.process_frame(accumulated_frame, direction)
                    await tts_service.process_frame(frame, direction)
                    logger.info(f"✅ Short response routed to {self.current_service} service")
                else:
                    # Fallback to default
                    logger.warning(f"No service for {self.current_service}, using default")
                    default_tts = self.tts_services[self.default_language]
                    await default_tts.process_frame(LLMFullResponseStartFrame(), direction)
                    accumulated_frame = LLMTextFrame(text=self.accumulated_text)
                    await default_tts.process_frame(accumulated_frame, direction)
                    await default_tts.process_frame(frame, direction)

            # Send end frame to the current service (if it was already set)
            elif self.current_service and self.current_service in self.tts_services:
                tts_service = self.tts_services[self.current_service]
                await tts_service.process_frame(frame, direction)

            # No service and no text - edge case, use default
            elif not self.current_service:
                logger.warning("Response ended with no service selected and no text, using default")
                default_tts = self.tts_services[self.default_language]
                await default_tts.process_frame(frame, direction)

            # Remember the last used service and reset for next response
            if self.current_service:
                self.last_used_service = self.current_service
            self.current_service = None
            self.accumulated_text = ""

        # Handle settings updates
        elif isinstance(frame, TTSUpdateSettingsFrame):
            for service in self.tts_services.values():
                await service.process_frame(frame, direction)

        else:
            # Pass through other frames
            await self.push_frame(frame, direction)

    def link(self, next_processor: FrameProcessor | None):
        """Links this processor to the pipeline chain."""
        super().link(next_processor)
        # Link child services for audio output
        for service in self.tts_services.values():
            service.link(next_processor)
            # Override queue_frame to prevent direct frame reception
            self._override_child_queue_frame(service)

    async def cleanup(self):
        """Cleanup resources and unsubscribe from language changes."""
        # Unsubscribe from language change notifications
        self.language_service.unsubscribe_from_language_changes(self._on_language_change)

        # Cleanup child services
        for service in self.tts_services.values():
            if hasattr(service, "cleanup"):
                await service.cleanup()

        logger.debug("MultiTTSRouter cleanup completed")
        await super().cleanup()

    def get_language_stats(self) -> dict:
        """Get language detection statistics."""
        return {"current_language": self.language_service.current_language, "default_language": self.default_language, "available_services": list(self.tts_services.keys()), "last_used_service": self.last_used_service, "current_service": self.current_service, "cache_stats": self.language_service.get_cache_stats()}
