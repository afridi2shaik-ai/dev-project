from typing import Optional
from pipecat.services.cartesia.stt import CartesiaSTTService, CartesiaLiveOptions
from app.core import settings
from app.schemas.services.stt import CartesiaSTTParams, CartesiaLanguage


def create_stt_service(
    base_url: Optional[str] = None,
    sample_rate: Optional[int] = None,
    params: Optional[CartesiaSTTParams] = None,
    live_options: Optional[dict] = None,  # We'll convert dict → CartesiaLiveOptions
):
    rate = sample_rate or 16000

    # Map language from your Enum → string
    lang = "en"
    if params and params.language:
        lang = params.language.value  # .value gives "hi", "te", etc.

    # Build live_options as a dict first
    options_dict = {
        "model": "ink-whisper",
        "language": lang,
        "encoding": "pcm_s16le",
        "sample_rate": rate,
    }

    # Override with user-provided live_options (if any)
    if live_options:
        options_dict.update(live_options)

    # Convert dict → CartesiaLiveOptions instance
    pipecat_options = CartesiaLiveOptions(**options_dict)

    return CartesiaSTTService(
        api_key=settings.CARTESIA_API_KEY,
        base_url=base_url ,
        live_options=pipecat_options,
    )