from enum import Enum
from typing import Any, Literal, Union

from pydantic import Field, field_validator

from app.core.constants import CUSTOMER_PROFILE_AI_REQUIRED_FIELDS
from app.schemas.core.call_lifecycle_schema import CallLifecycleConfig
from app.schemas.services.sllm import GroqSLLMConfig, SLLMCONFIG  
from ..base_schema import BaseSchema
from .audio_filter import KrispVivaFilterConfig
from .llm import LLMConfig, OpenAILLMConfig
from .stt import OpenAISTTConfig, STTConfig
from .tools import ToolsConfig
from .tts import SarvamTTSConfig, TTSConfig
from .vad import VADConfig


class PipelineMode(str, Enum):
    TRADITIONAL = "traditional"
    MULTIMODAL = "multimodal"
    AUDIO_CHAT = "audio_chat"
    TEXT = "text"


class CustomerDetails(BaseSchema):
    name: str | None = Field(None, description="The customer's name.")
    email: str | None = Field(None, description="The customer's email address.")
    history: str | None = Field(None, description="A summary of the customer's interaction history.")
    extra: dict[str, Any] | None = Field(None, description="Additional JSON data for custom details.")


class FirstMessageMode(str, Enum):
    SPEAK_FIRST = "speak_first"
    WAIT_FOR_USER = "wait_for_user"
    MODEL_GENERATED = "model_generated"


class SpeakFirstMessageConfig(BaseSchema):
    mode: Literal["speak_first"] = "speak_first"
    text: str = Field("Hello! How can I help you today?", description="The text for the assistant to speak first.")

    @field_validator("text")
    @classmethod
    def _validate_non_empty_text(cls, v: str) -> str:
        # Reject empty / whitespace-only text. Empty speak_first leads to "no audio" UX
        # and makes sessions appear stuck.
        if not v or not v.strip():
            raise ValueError("speak_first mode requires non-empty text")
        return v


class WaitForUserMessageConfig(BaseSchema):
    mode: Literal["wait_for_user"] = "wait_for_user"


class ModelGeneratedMessageConfig(BaseSchema):
    mode: Literal["model_generated"] = "model_generated"
    prompt: str | None = Field("Please introduce yourself to the user and ask how you can help.", description="The prompt for the model to generate the first message.")


FirstMessageConfig = Union[SpeakFirstMessageConfig, WaitForUserMessageConfig, ModelGeneratedMessageConfig]

# ==================================================================================================
# Agent Configuration
# ==================================================================================================


class IdleTimeoutConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable idle timeout detection.")
    timeout_seconds: float = Field(10.0, description="Seconds of inactivity before triggering the idle handler.")
    retries: int = Field(2, description="Number of times to prompt the user before ending the call.")
    prompt_templates: list[str] = Field(default_factory=lambda: ["Are you still there?", "If you're still there, please say something or I'll have to disconnect."], description="A list of prompts to use for each retry. The last one is the final message before hanging up.")


class FillerWordsConfig(BaseSchema):
    enabled: bool = Field(False, description="Enable or disable filler words for LLM delays.")
    filler_phrases: list[str] = Field(default_factory=lambda: ["Let me check that for you...", "I'll look into that right away...", "Okay, let me think about this...", "Hold on, I'm processing your request...", "One moment please...", "Let me see what I can find...", "I'm working on that now...", "Give me just a second..."], description="A list of filler phrases to choose from randomly.")
    delay_seconds: float = Field(0.5, description="Seconds to wait before speaking the filler text.")
    sllm_config: SLLMCONFIG = Field(default_factory=GroqSLLMConfig,description="Generic SLLM config. Defaults to Groq.")
    
class OpenAISummarizationConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str = Field("gpt-4o", description="The OpenAI model to use for summarization.")
    prompt_template: str = Field(
        """You are an intelligent call analysis assistant. Based on the following conversation transcript, please provide a summary and analysis in JSON format.

The JSON object should have the following structure:
{
  "summary": "<A concise summary of the conversation>",
  "outcome": "<'Interested' if the user showed clear interest in a product/service or agreed to a follow-up, otherwise 'Not Interested'>",
  "reasoning": "<A brief explanation for your outcome classification>"
}

Here is the conversation:""",
        description="Template for the summarization prompt.",
    )


class GeminiSummarizationConfig(BaseSchema):
    provider: Literal["gemini"] = "gemini"
    model: str = Field("gemini-1.5-flash", description="The Gemini model to use for summarization.")
    prompt_template: str = Field(
        """You are an intelligent call analysis assistant. Based on the following conversation transcript, please provide a summary and analysis in JSON format.

The JSON object should have the following structure:
{
  "summary": "<A concise summary of the conversation>",
  "outcome": "<'Interested' if the user showed clear interest in a product/service or agreed to a follow-up, otherwise 'Not Interested'>",
  "reasoning": "<A brief explanation for your outcome classification>"
}

Here is the conversation:""",
        description="Template for the summarization prompt.",
    )


SummarizationConfig = Union[OpenAISummarizationConfig, GeminiSummarizationConfig]


class ContextConfig(BaseSchema):
    """Configuration for session context building and management.
    Controls what contextual information is built and injected into the AI's system prompt.
    Allows fine-grained control over privacy, performance, and context relevance.
    """

    enabled: bool = Field(True, description="Master switch to enable or disable all session context building.")
    include_transport_details: bool = Field(True, description="Include transport mode (WebRTC, phone, WebSocket) and connection details.")
    include_user_details: bool = Field(False, description="Include user identification details (name, email, user ID) from authentication.")
    include_phone_numbers: bool = Field(True, description="Include phone numbers of participants in phone calls.")
    include_call_direction: bool = Field(True, description="Include call direction analysis (inbound vs outbound) for phone calls.")
    include_browser_info: bool = Field(True, description="Include browser and device information for WebRTC connections.")
    enhance_system_prompt: bool = Field(True, description="Automatically inject context information into the AI's system prompt.")
    privacy_mode: bool = Field(False, description="Enable privacy mode - masks sensitive information in context and logs.")
    call_lifecycle: CallLifecycleConfig | None = Field(None, description="Configuration for pre-call CRM enrichment and post-call CRM actions. Manages complete call lifecycle from customer lookup to post-call data updates.")


class CustomerProfileConfig(BaseSchema):
    """Controls usage of customer profile data in prompts and post-call updates."""

    use_in_prompt: bool = Field(True, description="Inject customer profile data into system prompts when available.")
    update_after_call: bool = Field(True, description="Update customer profiles (record call + AI extraction) after the call.")
    use_language_from_profile: bool = Field(False, description="Determine the conversation language from the customer profile's preferred language field. When disabled, falls back to the default language configured in the assistant.")
    ai_required_fields: list[str] = Field(
        default_factory=lambda: CUSTOMER_PROFILE_AI_REQUIRED_FIELDS.copy(),
        description=f"Fields the AI must extract for the customer profile; falls back to system defaults when not set. Defaults: {', '.join(CUSTOMER_PROFILE_AI_REQUIRED_FIELDS)}",
    )
    enforce_dnd: bool = Field(True, description="Master toggle for enforcing DND settings during telephony session creation.")
    dnd_policy: Literal["block_all","block_outbound_only","block_inbound_only","ignore"] = Field(
        "block_outbound_only",
        description="Controls which telephony directions are blocked when DND flags are set: 'block_all' blocks both directions, 'block_outbound_only' blocks outbound only, 'block_inbound_only' blocks inbound only, 'ignore' disables DND enforcement."
    )


class VoicemailDetectorConfig(BaseSchema):
    """Configuration for voicemail detection in outbound calls.

    The VoicemailDetector classifies whether a human answered or the call went to voicemail
    based on the user's first response. It works with both conversation flows:

    - **Bot speaks first** (speak_first/model_generated): The initial greeting is automatically
      allowed through, then classification happens when the user responds.
    - **User speaks first** (wait_for_user): Classification happens immediately when user speaks.

    Only enabled for telephony transports (Plivo, Twilio). WebRTC/WebSocket calls skip detection.
    Classification is definitive - once voicemail is detected, it's treated as voicemail 100%.
    """

    enabled: bool = Field(True, description="Enable voicemail detection for outbound telephony calls.")
    voicemail_response_delay: float = Field(
        2.0,
        ge=0.5,
        le=10.0,
        description="Seconds to wait after user stops speaking before triggering voicemail handler."
    )
    user_prompt: str = Field(
        "You've reached a voicemail. Leave a brief, professional message introducing yourself, "
        "mention why you called, and ask them to call back. Keep it under 30 words.",
        description="User prompt for LLM to generate voicemail message using agent's system prompt.",
    )


class SmartTurnConfig(BaseSchema):
    """Configuration for Smart Turn Detection."""

    enabled: bool = Field(False, description="Enable Smart Turn Detection for turn-taking.")
    stop_secs: float = Field(
        3.0,
        ge=0.1,
        le=10.0,
        description="Seconds of silence before forcing end-of-turn.",
    )
    pre_speech_ms: float = Field(
        0.0,
        ge=0.0,
        le=1000.0,
        description="Milliseconds of audio to include before speech starts.",
    )
    max_duration_secs: float = Field(
        8.0,
        ge=1.0,
        le=30.0,
        description="Maximum duration of a single turn segment in seconds.",
    )
    cpu_count: int = Field(
        1,
        ge=1,
        le=8,
        description="Number of CPU threads to use for local smart turn inference.",
    )


class AgentConfig(BaseSchema):
    name: str | None = Field(None, description="A descriptive name for the assistant.")
    pipeline_mode: PipelineMode = Field(PipelineMode.TRADITIONAL, description="The type of pipeline to use.")
    stt: STTConfig = Field(default_factory=OpenAISTTConfig, discriminator="provider")
    tts: TTSConfig = Field(default_factory=SarvamTTSConfig, discriminator="provider")
    llm: LLMConfig = Field(default_factory=OpenAILLMConfig, discriminator="provider")
    customer_details: CustomerDetails | None = Field(None, description="Details about the customer.")
    first_message: FirstMessageConfig = Field(default_factory=ModelGeneratedMessageConfig, discriminator="mode", description="Configuration for the assistant's first message.")
    report_only_initial_ttfb: bool = Field(True, description="If true, logs TTFB only once per service.")
    idle_timeout: IdleTimeoutConfig = Field(default_factory=IdleTimeoutConfig, description="Configuration for detecting and handling idle users.")
    filler_words: FillerWordsConfig = Field(default_factory=FillerWordsConfig, description="Configuration for speaking filler words during LLM delays.")
    summarization_enabled: bool = Field(True, description="Enable or disable call summarization.")
    summarization: SummarizationConfig = Field(default_factory=OpenAISummarizationConfig, discriminator="provider", description="Configuration for automatic call summarization.")
    tools: ToolsConfig | None = Field(None, description="Configuration for available tools (API integrations, etc.).")
    context_config: ContextConfig = Field(default_factory=ContextConfig, description="Configuration for session context building and AI contextual awareness.")
    customer_profile_config: CustomerProfileConfig = Field(default_factory=CustomerProfileConfig, description="Configuration for using and updating customer profiles.")
    extra_overrides: dict[str, Any] | None = Field(None, description="Extra override parameters.")
    vad: VADConfig = Field(default_factory=VADConfig, description="Configuration for Voice Activity Detection.")
    krisp_viva_filter: KrispVivaFilterConfig = Field(default_factory=KrispVivaFilterConfig, description="Krisp VIVA noise suppression filter configuration. Reduces background noise for improved speech recognition. Supports all sample rates including 8kHz telephony.")
    voicemail_detector: VoicemailDetectorConfig = Field(
        default_factory=VoicemailDetectorConfig,
        description="Configuration for voicemail detection in outbound calls."
    )
    smart_turn: SmartTurnConfig = Field(
        default_factory=SmartTurnConfig,
        description="Configuration for Smart Turn Detection.",
    )

# ----------------------------------------SoftHandoverTransfer----------------------------------------
