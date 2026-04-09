from pipecat.services.openai.tts import OpenAITTSService

from app.core import settings


def create_tts_service(model: str = "gpt-4o-mini-tts", voice: str = "nova", instructions: str | None = None, sample_rate: int | None = 24000):
    return OpenAITTSService(api_key=settings.OPENAI_API_KEY, model=model, voice=voice, instructions=instructions, sample_rate=sample_rate)
