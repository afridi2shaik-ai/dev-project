from typing import Any

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

from app.core import settings


def create_tts_service(voice_id: str = "2zRM7PkgwBPiau2jvVXc", model_id: str = "eleven_multilingual_v2", voice_settings: dict[str, Any] | None = None):
    return ElevenLabsTTSService(
        api_key=settings.ELEVENLABS_API_KEY,
        voice_id=voice_id,
        model=model_id,
        voice_settings=voice_settings,
        apply_text_normalization="on",
    )
