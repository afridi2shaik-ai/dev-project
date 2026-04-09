from typing import Optional

from pipecat.services.azure.tts import AzureTTSService
from pipecat.transcriptions.language import Language

from app.core import settings
from app.schemas.services.tts import AzureTTSParams
from loguru import logger


# Map user-provided short language codes ("en", "hi", etc.) to pipecat Language enums
# This is only needed because AzureTTSService.InputParams.language expects the pipecat enum
LANGUAGE_MAP = {
    "en": Language.EN_IN,
    "hi": Language.HI_IN,
    "te": Language.TE_IN,
    "ta": Language.TA_IN,
    "gu": Language.GU_IN,
    "mr": Language.MR_IN,
    "kn": Language.KN_IN,
}


def create_tts_service(
    voice: str = "en-IN-NeerjaNeural",          # ← Accept voice from config/user (e.g., "hi-IN-AartiNeural")
    sample_rate: int = 24000,
    params: Optional[AzureTTSParams] = None,
) -> AzureTTSService:
    
    if not settings.AZURE_SPEECH_API_KEY or not settings.AZURE_SPEECH_REGION:
        raise ValueError("Azure Speech credentials missing")

    # Use user-provided voice if available, else default to best Hindi voice
    selected_voice = voice or "en-IN-NeerjaNeural"  # Latest natural, bilingual (Hinglish) female Hindi voice (2025 release)
    logger.info(f"Azure TTS → Using voice: {selected_voice}")

    # Determine pipecat Language enum (default to Hindi)
    pipecat_lang = Language.HI_IN
    if params and params.language:
        # Use enum directly as dict key (AzureLanguage is str, Enum, so it works like Sarvam)
        pipecat_lang = LANGUAGE_MAP.get(params.language, Language.HI_IN)
        logger.info(f"Azure TTS → Language code from user: {params.language.value.upper()} → Mapped to pipecat enum")
    else:
        logger.info("Azure TTS → No language code provided → Using default (Hindi)")

    # Create InputParams – language enum is required by pipecat
    input_params = AzureTTSService.InputParams(
        emphasis=params.emphasis if params else None,
        language=pipecat_lang,
        pitch=params.pitch if params else None,
        rate=(params.rate if params else None) or "1.20",
        role=params.role if params else None,
        style=params.style if params else None,
        style_degree=params.style_degree if params else None,
        volume=params.volume if params else None,
    )

    service = AzureTTSService(
        api_key=settings.AZURE_SPEECH_API_KEY,
        region=settings.AZURE_SPEECH_REGION,
        voice=selected_voice,
        sample_rate=sample_rate,
        params=input_params,
    )

    # Enhanced cancellation error logging
    original_canceled = service._handle_canceled

    def detailed_canceled(self, evt):
        logger.error("=== AZURE TTS SYNTHESIS CANCELED ===")
        logger.error(f"Reason: {evt.result.cancellation_details.reason}")
        if evt.result.cancellation_details.error_details:
            logger.error(f"Error Details: {evt.result.cancellation_details.error_details}")
        if evt.result.cancellation_details.error_code:
            logger.error(f"Error Code: {evt.result.cancellation_details.error_code}")
        logger.error("=====================================")
        original_canceled(evt)

    service._handle_canceled = detailed_canceled.__get__(service)

    return service