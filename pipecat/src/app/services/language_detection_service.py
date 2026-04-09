"""Shared Language Detection Service

Centralized language detection with caching, extracted from MultiTTSRouter
to enable shared language awareness across multiple processors.
"""

import hashlib
import time
from collections.abc import Callable

from langdetect import DetectorFactory, detect
from loguru import logger

from app.core.constants import (
    LANGUAGE_CACHE_EXPIRY_SECONDS,
    LANGUAGE_CACHE_MAX_SIZE,
    LANGUAGE_MIN_TEXT_LENGTH,
)

# Set seed for consistent language detection
DetectorFactory.seed = 0


class LanguageDetectionService:
    """Centralized language detection with caching and event notifications.

    This service provides shared language detection capabilities across processors,
    with intelligent caching and event-driven language change notifications.
    """

    def __init__(self, default_language: str = "en", confidence_threshold: float = 0.7):
        """Initialize the language detection service.

        Args:
            default_language: Fallback language when detection fails
            confidence_threshold: Minimum confidence for language detection
        """
        self.default_language = default_language
        self.confidence_threshold = confidence_threshold

        # Language detection cache: {text_hash: (language, timestamp)}
        self._language_cache: dict[str, tuple[str, float]] = {}

        # Current language state
        self._current_language: str = default_language
        self._last_detection_time: float = time.time()

        # Event subscribers
        self._language_change_subscribers: list[Callable[[str], None]] = []

        logger.debug(f"LanguageDetectionService initialized with default: {default_language}")

    @property
    def current_language(self) -> str:
        """Get the currently detected language."""
        return self._current_language

    def detect_language(self, text: str, update_current: bool = True) -> str:
        """Detect language with caching and optional current language update.

        Args:
            text: Text to analyze for language detection
            update_current: Whether to update the current language state

        Returns:
            Detected language code (e.g., 'en', 'hi', 'es')
        """
        if not text or len(text.strip()) < LANGUAGE_MIN_TEXT_LENGTH:
            # For short text, return current language for consistency
            return self._current_language

        # Create secure cache key
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        current_time = time.time()

        # Check cache first
        if text_hash in self._language_cache:
            cached_lang, cached_time = self._language_cache[text_hash]
            if current_time - cached_time < LANGUAGE_CACHE_EXPIRY_SECONDS:
                logger.trace(f"Language cache hit: {cached_lang}")
                if update_current:
                    self._update_current_language(cached_lang)
                return cached_lang
            else:
                # Remove expired entry
                del self._language_cache[text_hash]

        # Perform language detection
        try:
            detected_language = detect(text.strip())
            logger.trace(f"Detected language: {detected_language} for text: {text[:50]}...")
        except Exception as e:
            logger.debug(f"Language detection failed: {e}, using default: {self.default_language}")
            detected_language = self.default_language

        # Cache the result
        self._cache_detection_result(text_hash, detected_language, current_time)

        if update_current:
            self._update_current_language(detected_language)

        return detected_language

    def subscribe_to_language_changes(self, callback: Callable[[str], None]):
        """Subscribe to language change notifications.

        Args:
            callback: Function to call when language changes, receives new language code
        """
        self._language_change_subscribers.append(callback)
        logger.debug(f"Added language change subscriber: {callback.__name__}")

    def unsubscribe_from_language_changes(self, callback: Callable[[str], None]):
        """Unsubscribe from language change notifications.

        Args:
            callback: Function to remove from notifications
        """
        if callback in self._language_change_subscribers:
            self._language_change_subscribers.remove(callback)
            logger.debug(f"Removed language change subscriber: {callback.__name__}")

    def force_language_change(self, new_language: str):
        """Manually set the current language and notify subscribers.

        Args:
            new_language: Language code to set as current
        """
        logger.info(f"Force language change: {self._current_language} → {new_language}")
        self._update_current_language(new_language)

    def get_cache_stats(self) -> dict[str, int]:
        """Get language detection cache statistics.

        Returns:
            Dictionary with cache size and hit information
        """
        return {
            "cache_size": len(self._language_cache),
            "max_cache_size": LANGUAGE_CACHE_MAX_SIZE,
            "cache_expiry_seconds": LANGUAGE_CACHE_EXPIRY_SECONDS,
        }

    def clear_cache(self):
        """Clear the language detection cache."""
        cache_size = len(self._language_cache)
        self._language_cache.clear()
        logger.debug(f"Cleared language detection cache ({cache_size} entries)")

    def _update_current_language(self, new_language: str):
        """Update current language and notify subscribers if changed.

        Args:
            new_language: The newly detected language
        """
        if new_language != self._current_language:
            old_language = self._current_language
            self._current_language = new_language
            self._last_detection_time = time.time()

            logger.debug(f"Language changed: {old_language} → {new_language}")

            # Notify all subscribers asynchronously
            for callback in self._language_change_subscribers:
                try:
                    callback(new_language)
                except Exception as e:
                    logger.warning(f"Language change callback failed: {e}")

    def _cache_detection_result(self, text_hash: str, language: str, timestamp: float):
        """Cache a language detection result with size management.

        Args:
            text_hash: Hash key for the text
            language: Detected language code
            timestamp: Detection timestamp
        """
        # Manage cache size
        if len(self._language_cache) >= LANGUAGE_CACHE_MAX_SIZE:
            self._cleanup_cache()

        self._language_cache[text_hash] = (language, timestamp)
        logger.trace(f"Cached language detection: {language}")

    def _cleanup_cache(self):
        """Clean up expired and oldest cache entries."""
        current_time = time.time()

        # Remove expired entries
        expired_keys = [key for key, (_, timestamp) in self._language_cache.items() if current_time - timestamp >= LANGUAGE_CACHE_EXPIRY_SECONDS]

        for key in expired_keys:
            del self._language_cache[key]

        # If still over limit, remove oldest entries
        if len(self._language_cache) >= LANGUAGE_CACHE_MAX_SIZE:
            # Sort by timestamp and remove oldest 50%
            sorted_items = sorted(
                self._language_cache.items(),
                key=lambda x: x[1][1],  # Sort by timestamp
            )

            entries_to_remove = len(sorted_items) // 2
            for key, _ in sorted_items[:entries_to_remove]:
                del self._language_cache[key]

        logger.debug(f"Cache cleanup completed, size: {len(self._language_cache)}")


# Global shared instance - can be accessed across processors
_global_language_service: LanguageDetectionService | None = None


def get_language_detection_service(default_language: str = "en", confidence_threshold: float = 0.7) -> LanguageDetectionService:
    """Get or create the global language detection service instance.

    Args:
        default_language: Default language for the service
        confidence_threshold: Confidence threshold for detection

    Returns:
        Shared LanguageDetectionService instance
    """
    global _global_language_service

    if _global_language_service is None:
        _global_language_service = LanguageDetectionService(default_language=default_language, confidence_threshold=confidence_threshold)
        logger.info("Created global LanguageDetectionService instance")

    return _global_language_service


def reset_language_detection_service():
    """Reset the global language detection service (useful for testing)."""
    global _global_language_service
    _global_language_service = None
    logger.debug("Reset global LanguageDetectionService")
