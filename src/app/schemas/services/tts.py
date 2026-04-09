from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import Field, field_validator

from ..base_schema import BaseSchema

# ==================================================================================================
# TTS Configuration Schemas
# ==================================================================================================


class SarvamLanguage(str, Enum):
    EN = "en"
    HI = "hi"
    TE = "te"
    TA = "ta"
    GU = "gu"
    MR = "mr"
    KN = "kn"


class SarvamTTSParams(BaseSchema):
    language: SarvamLanguage = Field(SarvamLanguage.EN, description="The language for the TTS.")
    pitch: float | None = Field(0.0, description="The pitch of the voice (-0.75 to 0.75).")
    pace: float | None = Field(0.85, description="Speech pace multiplier (0.3 to 3.0). Lower = slower speech with more natural pauses. Default 0.85 for conversational pace.")
    enable_preprocessing: bool = Field(True, description="Enable text preprocessing for natural pauses at punctuation.")


class SarvamTTSConfig(BaseSchema):
    provider: Literal["sarvam"] = "sarvam"
    voice_id: str = Field("vidya", description="The voice ID for TTS.")
    model: str = Field("bulbul:v2", description="The TTS model to use.")
    sample_rate: int = Field(24000, description="The sample rate of the audio.")
    params: SarvamTTSParams | None = Field(default_factory=SarvamTTSParams, description="Additional TTS parameters.")

    @field_validator("voice_id")
    def validate_voice_id(cls, v):
        allowed_voices = ["anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"]
        if v not in allowed_voices:
            raise ValueError(f"Unsupported Sarvam voice ID: {v}. Must be one of {allowed_voices}")
        return v


class ElevenLabsTTSConfig(BaseSchema):
    provider: Literal["elevenlabs"] = "elevenlabs"
    voice_id: str = Field("2zRM7PkgwBPiau2jvVXc", description="The voice ID for TTS.")
    model_id: str = Field("eleven_multilingual_v2", description="The ElevenLabs model to use.")
    voice_settings: dict[str, Any] | None = Field(None, description="A dictionary for voice settings like stability and similarity_boost.")

    @field_validator("voice_id")
    def validate_voice_id(cls, v):
        if not v:
            raise ValueError(f"Unsupported OpenAI voice: {v}.")
        return v


class OpenAITTSConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str | None = Field("gpt-4o-mini-tts", description="The TTS model to use.")
    voice: str | None = Field("nova", description="The voice to use for TTS.")
    instructions: str | None = Field("Speak in a clear Indian English accent — neutral, polite, and professional.", description="Special instructions for TTS generation.")
    sample_rate: int | None = Field(24000, description="The sample rate of the audio.")

    @field_validator("voice")
    def validate_voice(cls, v):
        allowed_voices = ["nova", "alloy", "shimmer"]
        if v not in allowed_voices:
            raise ValueError(f"Unsupported OpenAI voice: {v}. Must be one of {allowed_voices}")
        return v
class AzureLanguage(str, Enum):
    EN = "en"
    HI = "hi"
    TE = "te"
    TA = "ta"
    GU = "gu"
    MR = "mr"
    KN = "kn"
    

class AzureTTSParams(BaseSchema):
    emphasis: str | None = Field(None, description="Emphasis level for speech (‘strong’, ‘moderate’, ‘reduced’).")
    language: AzureLanguage | None = Field(None, description="Language for synthesis.")
    pitch: str | None = Field(None, description="Voice pitch adjustment.")
    rate: str | None = Field(None, description="Speech rate multiplier.")
    role: str | None = Field(None, description="Voice role for expression.")
    style: str | None = Field(None, description="Speaking style.")
    style_degree: str | None = Field(None, description="Intensity of the speaking style (0.01 to 2.0).")
    volume: str | None = Field(None, description="Volume level.")

class AzureTTSConfig(BaseSchema):
    provider: Literal["azure"] = "azure"
    voice: str = Field("en-IN-NeerjaNeural", description="The voice ID for TTS.")
    sample_rate: int = Field(24000, description="The sample rate of the audio.")
    params: AzureTTSParams | None = Field(default_factory=AzureTTSParams, description="Additional TTS parameters.")

class CartisiaTTSConfig(BaseSchema):
    provider: Literal["cartesia"] = "cartesia"
    model: str = Field("sonic-3", description="The Cartisia TTS model to use.")
    voice_id: str = Field("95d51f79-c397-46f9-b49a-23763d3eaa2d", description="The voice preset to use for Cartisia TTS.")
    language: str | None = Field("en", description="Language code for TTS output.")
    volume: Optional[float] = Field(1.0, description="Volume multiplier for TTS output (0.5 to 2.0).")
    speed: Optional[float] = Field(1.0, description="Speed multiplier for TTS output (0.6 to 1.5).")
    emotion: Optional[str] = Field("neutral", description="Emotion preset for TTS output (e.g., 'neutral', 'excited', 'sad').")

DynamicInnerTTSConfig = Annotated[
    Union[
        SarvamTTSConfig,
        ElevenLabsTTSConfig,
        OpenAITTSConfig,
        CartisiaTTSConfig,
        AzureTTSConfig,
    ],
    Field(discriminator="provider"),
]


class DynamicTTSConfig(BaseSchema):
    provider: Literal["dynamic"] = "dynamic"
    default_language: str = Field("en", description="Default language to use if detection fails or is unsupported.")
    configs: Dict[str, DynamicInnerTTSConfig] = Field(
        ...,
        description="Dictionary of TTS configurations keyed by language code (e.g., 'en', 'hi').",
    )





TTSConfig = Union[SarvamTTSConfig, ElevenLabsTTSConfig, OpenAITTSConfig, DynamicTTSConfig, CartisiaTTSConfig, AzureTTSConfig]
