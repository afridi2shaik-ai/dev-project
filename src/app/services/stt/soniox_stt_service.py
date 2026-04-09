from typing import Optional, List

from pipecat.services.soniox.stt import SonioxSTTService, SonioxInputParams

from app.core import settings


def create_stt_service(
    model: str = "stt-rt-v4",
    language: List[str] = None,
    language_hints_strict:bool= None,
    # base_url: Optional[str] = None,
    # sample_rate: Optional[int] = None,
    # enable_speaker_diarization: bool = False,
    # enable_language_identification: bool = False,
):

    params = SonioxInputParams(
        model=model,
        language_hints=language,
        language_hints_strict=language_hints_strict,
        # enable_speaker_diarization=enable_speaker_diarization,
        # enable_language_identification=enable_language_identification,
    )
    kwargs = {"api_key": settings.SONIOX_API_KEY, "params": params}
  
    return SonioxSTTService(**kwargs)
