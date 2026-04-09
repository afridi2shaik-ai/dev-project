from typing import Optional
import aiohttp
from pipecat.services.elevenlabs.stt import ElevenLabsSTTService
from pipecat.transcriptions.language import Language
from app.core import settings


def create_stt_service(
    aiohttp_session: aiohttp.ClientSession,
    language: str = "en",     # e.g. "en", "hi", "te"
    model: str = "scribe_v1",
):
    # Map raw language code (str) -> Pipecat Language enum
    language_map = {
        "en": Language.EN,
        "hi": Language.HI,
        "te": Language.TE,
        "ta": Language.TA,
        "gu": Language.GU,
        "mr": Language.MR,
        "kn": Language.KN,
    }

    # Default to English if not matched
    pipecat_language = language_map.get(language, Language.EN)

    return ElevenLabsSTTService(
        api_key=settings.ELEVENLABS_API_KEY,
        aiohttp_session=aiohttp_session,
        model=model,
        language=pipecat_language,   # <-- correct value
    )
