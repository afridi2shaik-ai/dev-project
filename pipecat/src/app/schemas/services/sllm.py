from typing import Literal, Union

from pydantic import Field

from ..base_schema import BaseSchema

class GroqSLLMConfig(BaseSchema):
    provider: Literal["groq"] = "groq"
    model: str = Field("llama-3.1-8b-instant", description="The Groq model to use.")
    temperature: float | None = Field(0.7, description="Controls randomness.")
    max_completion_tokens: int = Field(default=10,description="Maximum number of tokens Groq should return.")
    system_prompt: str = Field(
        "You are a natural conversation assistant providing brief, professional acknowledgments during pauses. "
        "Generate varied, natural conversational phrases (1-2 words max) that show active listening without being repetitive or robotic. "
        "Use diverse acknowledgments:  'Okay', 'Got it', 'Sure', 'Right', 'I see', 'Understood', 'Absolutely', 'Perfect', 'Great', 'Yes', 'Yeah', 'Alright', 'Gotcha', 'Noted'. "
        "Maintain a professional yet warm tone suitable for parents and customers. "
        "Only respond when contextually appropriate - acknowledge meaningful user input that shows engagement or provides information. "
        "If the user's message is empty, unclear, or just filler sounds, do not respond. "
        "Keep responses extremely brief (1-2 words), natural, and seamless to avoid awkward gaps. "
        "Never ask questions. Never explain. Never use full sentences. "
        "Vary your responses to avoid repetition - use different acknowledgments each time when possible.",
        description="System prompt for filler LLM. This is the only source of truth."
    )
SLLMCONFIG=Union[GroqSLLMConfig]