from typing import Any, Literal, Union, List

from pydantic import Field, field_validator

from ..base_schema import BaseSchema
from pydantic import BaseModel
from enum import Enum

# ==================================================================================================
# STT Configuration Schemas
# ==================================================================================================


class DeepgramLiveOptions(BaseSchema):
    model: str = Field("nova-3-general", description="The Deepgram STT model to use.")
    language: str | None = Field("en-US", description="The language of the input audio (e.g., 'en-US').")
    tier: str | None = Field(None, description="The tier of the model to use (e.g., 'nova' or 'base').")
    keywords: list[str] = Field(default_factory=list, description="Keywords to improve recognition accuracy.")
    smart_format: bool = Field(True, description="Enable smart formatting.")
    punctuate: bool = Field(True, description="Enable punctuation.")
    numerals: bool = Field(True, description="Enable numeral conversion.")
    profanity_filter: bool = Field(True, description="Filter profanity.")
    vad_events: bool = Field(False, description="Enable Voice Activity Detection events.")
    endpointing: int | None = Field(None, description="Endpointing in milliseconds.")
    interim_results: bool = Field(True, description="Receive interim results.")


class DeepgramSTTConfig(BaseSchema):
    provider: Literal["deepgram"] = "deepgram"
    url: str | None = Field(None, description="Custom WebSocket URL for Deepgram.")
    base_url: str | None = Field(None, description="Custom base URL for the REST API.")
    sample_rate: int | None = Field(None, description="The sample rate of the audio.")
    live_options: DeepgramLiveOptions = Field(default_factory=DeepgramLiveOptions, description="Deepgram live transcription options.")
    addons: dict[str, Any] | None = Field(None, description="Additional Deepgram add-ons.")


class GoogleSTTConfig(BaseSchema):
    provider: Literal["google"] = "google"
    language: str = Field("en-IN", description="The primary language for STT.")
    alternative_language_codes: list[str] = Field(default_factory=lambda: ["hi-IN", "te-IN"], description="Alternative languages for STT.")
    model: str | None = Field("latest_long", description="The STT model to use.")
    enable_automatic_language_detection: bool = Field(True, description="Enable automatic language detection.")

    @field_validator("language")
    def validate_language(cls, v):
        allowed_languages = ["en-IN", "hi-IN", "te-IN", "en-US", "es-ES"]
        if v not in allowed_languages:
            raise ValueError(f"Unsupported language code: {v}. Must be one of {allowed_languages}")
        return v

    @field_validator("alternative_language_codes")
    def validate_alternative_languages(cls, v):
        allowed_languages = ["en-IN", "hi-IN", "te-IN", "en-US", "es-ES"]
        for code in v:
            if code not in allowed_languages:
                raise ValueError(f"Unsupported alternative language code: {code}. Must be one of {allowed_languages}")
        return v


class OpenAISTTConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str | None = Field("whisper-1", description="The STT model to use.")
    language: str | None = Field(None, description="The language of the input audio (ISO-639-1 format).")
    prompt: str | None = Field(None, description="A prompt to improve recognition accuracy.")

    @field_validator("model")
    def validate_model(cls, v):
        allowed_models = ["whisper-1", "gpt-4o-transcribe","gpt-4o-transcribe-diarize"]
        if v not in allowed_models:
            raise ValueError(f"Unsupported OpenAI STT model: {v}. Must be one of {allowed_models}")
        return v


class CartesiaLiveOptions(BaseModel):

    model: str = Field(default="ink-whisper",description="Cartesia STT model to use (default: 'ink-whisper').",)
    language: str|None = Field("en",description="Language code for transcription (e.g., 'en', 'es', 'fr').",)
    encoding: str = Field(default="pcm_s16le",description="Audio encoding format (default: 'pcm_s16le').",)
    sample_rate: int = Field(default=16000,description="Audio sample rate in Hz (default: 16000).",ge=8000,)
    

class  CartesiaLanguage(str, Enum):
    EN = "en"
    HI = "hi"
    TE = "te"
    TA = "ta"
    GU = "gu"
    MR = "mr"
    KN = "kn"

class  CartesiaSTTParams(BaseSchema):
    language:  CartesiaLanguage = Field( CartesiaLanguage.EN, description="The language for the TTS.")
    pitch: float | None = Field(None, description="The pitch of the voice.")
    pace: float | None = Field(None, description="The pace of the voice.")

class CartesiaSTTConfig(BaseModel):

    provider: Literal["cartesia"] = "cartesia"
    base_url: str | None = Field(None, description="Base URL for Cartesia STT service.")
    sample_rate: int | None = Field(None, description="The sample rate of the audio.")
    live_options: CartesiaLiveOptions = Field(
        default_factory=CartesiaLiveOptions,
        description="Configuration options for Cartesia Live STT service.",
    )

class ElevenLabsSTTConfig(BaseSchema):
    provider: Literal["elevenlabs"] = "elevenlabs"
    model: str = Field("scribe_v1", description="The ElevenLabs STT model to use.")
    language: str = Field("en", description="Target language code")


class SonioxSTTConfig(BaseSchema):
    provider: Literal["soniox"] = "soniox"
    model: str = Field("stt-rt-v4", description="The Soniox STT model to use.")
    language: List[str] | None = Field(["en"], description="Language for transcription (e.g. 'en', 'es'). Passed to Soniox as language_hints array.")
    language_hints_strict: bool|None = Field(True, description="Whether to strictly enforce language hints in Soniox STT.")


STTConfig = Union[GoogleSTTConfig, OpenAISTTConfig, DeepgramSTTConfig, CartesiaSTTConfig, ElevenLabsSTTConfig, SonioxSTTConfig]
