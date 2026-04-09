from typing import Any

from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions

from app.core import settings
from app.schemas.services.stt import DeepgramLiveOptions as AppDeepgramLiveOptions


def create_stt_service(
    url: str | None = None,
    base_url: str | None = None,
    sample_rate: int | None = None,
    live_options: AppDeepgramLiveOptions | None = None,
    addons: dict[str, Any] | None = None,
):
    # The SDK expects a pipecat.services.deepgram.stt.LiveOptions object.
    # We create it from our Pydantic schema's dictionary representation.
    sdk_live_options = LiveOptions(**live_options.model_dump()) if live_options else None

    return DeepgramSTTService(
        api_key=settings.DEEPGRAM_API_KEY,
        url=url or "",
        base_url=base_url or "",
        sample_rate=sample_rate,
        live_options=sdk_live_options,
        addons=addons,
    )
