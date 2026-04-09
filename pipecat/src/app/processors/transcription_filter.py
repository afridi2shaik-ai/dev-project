"""Transcription Filter Processor

This processor filters out empty, whitespace-only, or meaningless transcriptions
to prevent them from reaching the LLM and causing empty responses.

Also blocks all transcriptions during warm transfer to prevent the agent from
talking while the customer is on hold waiting for a supervisor.
"""

import inspect
import re
from typing import Any, Callable

from loguru import logger
from pipecat.frames.frames import Frame, InterimTranscriptionFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptionFilter(FrameProcessor):
    """Filters out empty or meaningless transcriptions to prevent empty LLM responses.

    This is especially important when using OpenAI STT, which can send empty
    transcriptions when it can't detect clear speech, leading to application
    crashes with certain TTS services like Sarvam.
    
    Also blocks all transcriptions during warm transfer to prevent the agent from
    talking while the customer is on hold waiting for a supervisor.
    """

    def __init__(self, min_length: int = 3, filter_patterns: list | None = None):
        """Initialize the transcription filter.

        Args:
            min_length: Minimum character length for valid transcriptions
            filter_patterns: Additional regex patterns to filter out
        """
        super().__init__()
        self._min_length = min_length
        
        # Session context for warm transfer check
        self._session_manager = None
        self._session_id: str | None = None
        self._session_metadata_supplier: Callable[[], Any] | None = None
        
        # Cache for warm transfer state to avoid frequent DB lookups
        self._warm_transfer_active_cache: bool = False
        self._cache_check_counter: int = 0
        self._cache_check_interval: int = 10  # Check DB every 10 transcriptions

        # Default patterns to filter out common meaningless transcriptions
        self._filter_patterns = filter_patterns or [
            r"^[.,!?\s]*$",  # Only punctuation and whitespace
            r"^(uh|um|ah|er|hmm)\s*$",  # Filler sounds only
            r"^[a-zA-Z]\s*$",  # Single letters
            r"^\s*$",  # Only whitespace
        ]

        # Compile patterns for efficiency
        self._compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self._filter_patterns]

        logger.debug(f"TranscriptionFilter initialized with min_length={min_length}")
    
    def set_session_context(self, session_manager, session_id: str, metadata_supplier: Callable[[], Any] | None = None):
        """Set session context for warm transfer checking.
        
        Args:
            session_manager: SessionManager instance for DB lookups
            session_id: Current session ID
            metadata_supplier: Optional callable that returns current session metadata
        """
        self._session_manager = session_manager
        self._session_id = session_id
        self._session_metadata_supplier = metadata_supplier
        logger.debug(f"TranscriptionFilter session context set for {session_id}")
    
    async def _is_warm_transfer_active(self) -> bool:
        """Check if warm transfer is currently active for this session.
        
        Uses caching to avoid frequent DB lookups during active calls.
        """
        # Increment counter and check if we should refresh the cache
        self._cache_check_counter += 1
        
        # Only check DB periodically or if cache is empty
        if self._cache_check_counter < self._cache_check_interval and self._cache_check_counter > 1:
            return self._warm_transfer_active_cache
        
        self._cache_check_counter = 0
        
        # Try metadata supplier first (fastest)
        if self._session_metadata_supplier:
            try:
                metadata_candidate = self._session_metadata_supplier()
                metadata = await metadata_candidate if inspect.isawaitable(metadata_candidate) else metadata_candidate
                if isinstance(metadata, dict):
                    self._warm_transfer_active_cache = bool(metadata.get("warm_transfer_active"))
                    return self._warm_transfer_active_cache
            except Exception as exc:
                logger.debug(f"Unable to fetch metadata via supplier: {exc}")
        
        # Fallback to session manager lookup
        if self._session_manager and self._session_id:
            try:
                session = await self._session_manager.get_session(self._session_id)
                if session and session.metadata:
                    metadata_obj = session.metadata
                    if isinstance(metadata_obj, dict):
                        self._warm_transfer_active_cache = bool(metadata_obj.get("warm_transfer_active"))
                    elif hasattr(metadata_obj, "get"):
                        self._warm_transfer_active_cache = bool(metadata_obj.get("warm_transfer_active"))
                    else:
                        self._warm_transfer_active_cache = False
                    return self._warm_transfer_active_cache
            except Exception as exc:
                logger.debug(f"Unable to fetch session for warm transfer check: {exc}")
        
        return self._warm_transfer_active_cache

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and filter out empty/meaningless transcriptions.
        
        Also blocks ALL transcriptions during warm transfer to prevent
        the agent from talking while the customer is on hold.
        """
        # CRITICAL: Call super().process_frame() first for proper initialization
        await super().process_frame(frame, direction)

        # Check for transcription frames (both final and interim)
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            # CRITICAL: Block all transcriptions during warm transfer
            # This prevents the LLM from responding while the customer is on hold
            if await self._is_warm_transfer_active():
                logger.debug(f"🚫 Warm transfer active - blocking transcription: '{frame.text[:50] if frame.text else ''}...'")
                return  # Don't pass this frame downstream - customer is on hold
            
            # Only check validity for final transcriptions, not interim
            if isinstance(frame, TranscriptionFrame):
                if not self._is_valid_transcription(frame.text):
                    # Log the filtered transcription for debugging
                    logger.debug(f"Filtered empty/meaningless transcription: '{frame.text}'")
                    return  # Don't pass this frame downstream

                # Log valid transcriptions (for debugging)
                logger.debug(f"Passing valid transcription: '{frame.text}'")

        # Pass all other frames or valid transcriptions downstream
        await self.push_frame(frame, direction)

    def _is_valid_transcription(self, text: str) -> bool:
        """Check if a transcription is valid and meaningful.

        Args:
            text: The transcription text to validate

        Returns:
            True if the transcription should be processed, False if it should be filtered
        """
        if not text:
            return False

        # Check minimum length
        if len(text.strip()) < self._min_length:
            return False

        # Check against filter patterns
        return all(not pattern.match(text.strip()) for pattern in self._compiled_patterns)

    def set_warm_transfer_active(self, active: bool):
        """Manually set warm transfer state for immediate effect.
        
        This is faster than waiting for DB lookup and should be called
        by the warm_transfer_tool when starting/ending a transfer.
        
        Args:
            active: True when warm transfer starts, False when it completes
        """
        self._warm_transfer_active_cache = active
        self._cache_check_counter = 0  # Reset counter to force next check from DB
        logger.info(f"🔇 TranscriptionFilter warm_transfer_active manually set to {active}")
    
    async def cleanup(self):
        """Cleanup resources."""
        logger.debug("TranscriptionFilter cleanup completed")
        await super().cleanup()
