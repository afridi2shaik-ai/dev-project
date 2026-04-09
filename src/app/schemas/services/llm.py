from typing import Literal, Union

from pydantic import Field, field_validator

from ..base_schema import BaseSchema

# ==================================================================================================
# LLM Configuration Schemas
# ==================================================================================================


class OpenAILLMConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str | None = Field("gpt-4.1-nano", description="The LLM model to use.")
    temperature: float | None = Field(None, description="Controls randomness. Lower is more deterministic.")
    top_p: float | None = Field(None, description="Nucleus sampling. Considers tokens with top_p probability mass.")
    max_tokens: int | None = Field(None, description="The maximum number of tokens to generate.")
    presence_penalty: float | None = Field(None, description="Penalty for new tokens based on their presence so far.")
    frequency_penalty: float | None = Field(None, description="Penalty for new tokens based on their frequency so far.")
    system_prompt_template: str = Field("You are a  default AI assistant. Respond naturally and keep your answers conversational. Ask the user to recheck the configurations", description="Template for the system prompt.")

    @field_validator("model")
    def validate_model(cls, v):
        allowed_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4.1-nano", "gpt-4.1-mini", "gpt-5-nano", "gpt-5-mini", "gpt-4.1", "gpt-5", "o4-mini"]
        if v not in allowed_models:
            raise ValueError(f"Unsupported OpenAI model: {v}. Must be one of {allowed_models}")
        return v


class GeminiLLMConfig(BaseSchema):
    provider: Literal["gemini"] = "gemini"
    model: str = Field("gemini-2.0-flash-live-001", description="The Gemini model to use.")
    voice_id: str = Field("Prik", description="The voice ID for the Gemini model.")
    temperature: float | None = Field(0.7, description="Controls randomness.")

LLMConfig = Union[OpenAILLMConfig, GeminiLLMConfig]
