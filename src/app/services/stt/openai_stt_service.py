from pipecat.services.openai.stt import OpenAISTTService

from app.core import settings


def create_stt_service(model: str = "gpt-4o-transcribe", language: str | None = None, prompt: str | None = None):
    return OpenAISTTService(api_key=settings.OPENAI_API_KEY, model=model, language=language, prompt=prompt)
