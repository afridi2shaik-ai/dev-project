from loguru import logger
from pipecat.services.sarvam.tts import Language, SarvamTTSService

from app.core import settings
from app.schemas.services.tts import SarvamTTSParams


def create_tts_service(voice_id: str = "vidya", model: str = "bulbul:v2", sample_rate: int = 24000, params: SarvamTTSParams | None = None):
    """Create Sarvam TTS service with optimized settings for natural speech pacing.
    
    Key parameters for pause control:
    - pace: 0.85 (slower than default 1.0 for natural pauses)
    - enable_preprocessing: True (text normalization for punctuation-based pauses)
    - pitch: 0.0 (natural pitch)
    
    Note: min_buffer_size and max_chunk_length use SDK defaults (50 and 200)
    to ensure compatibility with Sarvam API.
    """
    if params:
        # Map our schema enum to the pipecat enum
        language_map = {
            "en": Language.EN,
            "hi": Language.HI,
            "te": Language.TE,
            "ta": Language.TA,
            "gu": Language.GU,
            "mr": Language.MR,
            "kn": Language.KN,
        }
        pipecat_language = language_map.get(params.language, Language.EN)

        # ✅ Create InputParams with pace control for natural pauses
        # IMPORTANT: Sarvam API rejects None values, so we provide sensible defaults
        # Extract values with fallbacks FIRST to avoid any Pydantic quirks
        pitch_value = 0.0 if params.pitch is None else float(params.pitch)
        pace_value = 0.85 if params.pace is None else float(params.pace)
        
        logger.debug(f"Creating Sarvam TTS InputParams: pitch={pitch_value}, pace={pace_value}, lang={pipecat_language}")
        
        # Use only essential parameters - let SDK use defaults for buffer sizes
        input_params = SarvamTTSService.InputParams(
            language=pipecat_language,
            pitch=pitch_value,
            pace=pace_value,
            enable_preprocessing=True if params.enable_preprocessing is None else params.enable_preprocessing,
        )
    else:
        # Default: optimized for natural speech with pauses
        logger.debug("Creating Sarvam TTS InputParams with defaults: pitch=0.0, pace=0.85")
        input_params = SarvamTTSService.InputParams(
            pitch=0.0,  # Default natural pitch
            pace=0.85,  # Slower pace for natural pauses
            enable_preprocessing=True,
        )

    return SarvamTTSService(api_key=settings.SARVAM_API_KEY, voice_id=voice_id, model=model, sample_rate=sample_rate, params=input_params)
