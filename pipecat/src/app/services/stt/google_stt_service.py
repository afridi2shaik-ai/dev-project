from pipecat.services.google.stt import GoogleSTTService
from pipecat.transcriptions.language import Language


def create_stt_service(
    language: str,
    alternative_language_codes: list[str] | None = None,
    model: str | None = None,
    enable_automatic_language_detection: bool = False,
):
    # Ensure the primary language is a tuple as expected by the service
    languages = (Language(language),)

    return GoogleSTTService(
        languages=languages,
        alternative_language_codes=alternative_language_codes,
        model=model,
        enable_automatic_language_detection=enable_automatic_language_detection,
    )
