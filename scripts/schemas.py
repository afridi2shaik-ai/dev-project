from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


# Base Schema
# Note: BaseSchema uses extra="allow" for internal flexibility (migrations, config merging)
# For API validation, use validate_agent_config_strict() function for strict checking
class BaseSchema(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        extra="allow",  # Allow extra fields for internal operations
    )


# VAD Schemas
class VADConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable Voice Activity Detection.")
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold for voice detection.")
    start_secs: float = Field(0.2, ge=0.0, le=2.0, description="Time in seconds user must speak before VAD confirms speech has started.")
    stop_secs: float = Field(0.8, ge=0.0, le=5.0, description="Time in seconds of silence required before confirming speech has stopped.")
    min_volume: float = Field(0.6, ge=0.0, le=1.0, description="Minimum audio volume threshold for speech detection.")
    preset: Optional[str] = Field(None, description="Use a preset configuration: 'conversation', 'turn_detection', 'ivr', 'sensitive', 'strict'")
    auto_adjust_for_turn_detection: bool = Field(True, description="Automatically set stop_secs=0.2 when Smart Turn Detection is enabled.")

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v):
        if v is not None:
            valid_presets = ["conversation", "turn_detection", "ivr", "sensitive", "strict"]
            if v not in valid_presets:
                raise ValueError(f"Invalid preset '{v}'. Must be one of: {valid_presets}")
        return v


# Audio Filter Schemas
class KrispVivaFilterConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable Krisp VIVA noise suppression.")
    model_path: Optional[str] = Field(None, description="Path to the Krisp VIVA model file.")
    noise_suppression_level: int = Field(0, description="Noise suppression level (0-10).")


# TTS Schemas
class SarvamTTSConfig(BaseSchema):
    provider: Literal["sarvam"] = "sarvam"
    voice_id: str = Field("ai-voice-dev-001", description="The voice ID to use.")
    model: str = Field("v1-multi", description="The model to use.")
    sample_rate: int = Field(24000, description="The sample rate of the audio.")
    params: Optional[Dict[str, Any]] = Field(None, description="Additional parameters.")


class ElevenLabsTTSConfig(BaseSchema):
    provider: Literal["elevenlabs"] = "elevenlabs"
    voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", description="The voice ID to use.")
    model_id: str = Field("eleven_turbo_v2", description="The model ID to use.")
    voice_settings: Optional[Dict[str, Any]] = Field(None, description="Voice settings.")


class OpenAITTSConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str = Field("tts-1", description="The model to use.")
    voice: str = Field("alloy", description="The voice to use.")
    instructions: Optional[str] = Field(None, description="Instructions for the TTS.")
    sample_rate: int = Field(24000, description="The sample rate of the audio.")

class CartisiaTTSConfig(BaseSchema):
    provider: Literal["cartisia"] = "cartisia"
    voice_id: str = Field("your-voice-id", description="The voice ID to use.")
    model: str = Field("your-model", description="The model to use.")
    language: str = Field("en", description="The language of the voice.")
    
class AzureTTSConfig(BaseSchema):
    provider: Literal["azure"] = "azure"
    voice: Optional[str] = Field(None, description="The specific voice to use (e.g., 'hi-IN-AartiNeural').")
    sample_rate: int = Field(24000, description="The sample rate of the audio.")
    params: Optional[Dict[str, Any]] = Field(None, description="Additional TTS parameters.")

class DynamicTTSConfig(BaseSchema):
    provider: Literal["dynamic"] = "dynamic"
    default_language: str = Field("en-US", description="The default language to use.")
    configs: Dict[str, Union[SarvamTTSConfig, ElevenLabsTTSConfig, OpenAITTSConfig, CartisiaTTSConfig,AzureTTSConfig]] = Field(..., description="Dictionary of language codes to TTS configurations.")


TTSConfig = Union[SarvamTTSConfig, ElevenLabsTTSConfig, OpenAITTSConfig, CartisiaTTSConfig,AzureTTSConfig, DynamicTTSConfig]


# STT Schemas
class DeepgramLiveOptions(BaseSchema):
    model: str = Field("nova-2", description="The model to use.")
    language: str = Field("en-US", description="The language to use.")
    punctuate: bool = Field(True, description="Add punctuation to the transcript.")
    interim_results: bool = Field(True, description="Receive interim results.")


class DeepgramSTTConfig(BaseSchema):
    provider: Literal["deepgram"] = "deepgram"
    url: Optional[str] = Field(None, description="The URL for the Deepgram API.")
    base_url: Optional[str] = Field(None, description="The base URL for the Deepgram API.")
    sample_rate: int = Field(16000, description="The sample rate of the audio.")
    live_options: DeepgramLiveOptions = Field(default_factory=DeepgramLiveOptions)
    addons: Optional[Dict[str, Any]] = Field(None, description="Additional add-ons.")


class GoogleSTTConfig(BaseSchema):
    provider: Literal["google"] = "google"
    language: str = Field("en-US", description="The language to use.")
    alternative_language_codes: Optional[List[str]] = Field(None, description="Alternative language codes.")
    model: str = Field("telephony", description="The model to use.")
    enable_automatic_language_detection: bool = Field(False, description="Enable automatic language detection.")


class OpenAISTTConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str = Field("whisper-1", description="The model to use.")
    language: Optional[str] = Field(None, description="The language to use.")
    prompt: Optional[str] = Field(None, description="A prompt to guide the transcription.")

class CartesiaSTTConfig(BaseSchema):
    provider: Literal["cartesia"] = "cartesia"
    base_url: Optional[str] = Field(None, description="The base URL for the Cartesia API.")
    sample_rate: int = Field(16000, description="The sample rate of the audio.")
    live_options: Optional[Dict[str, Any]] = Field(None, description="Live options for transcription.")


class SonioxSTTConfig(BaseSchema):
    provider: Literal["soniox"] = "soniox"
    model: str = Field("stt-rt-v4", description="The Soniox STT model to use.")
    language: str = Field("en", description="Language for transcription (e.g. 'en', 'es'). Passed to Soniox as language_hints array.")
    base_url: Optional[str] = Field(None, description="Custom base URL for Soniox API.")
    enable_speaker_diarization: bool = Field(False, description="Enable speaker diarization.")
    enable_language_identification: bool = Field(False, description="Enable language identification.")


STTConfig = Union[DeepgramSTTConfig, GoogleSTTConfig, OpenAISTTConfig, CartesiaSTTConfig, SonioxSTTConfig]


# LLM Schemas
class OpenAILLMConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str = Field("gpt-4o", description="The model to use.")
    temperature: float = Field(0.7, description="The temperature for sampling.")
    top_p: Optional[float] = Field(None, description="The top-p for sampling.")
    max_tokens: Optional[int] = Field(None, description="The maximum number of tokens to generate.")
    presence_penalty: Optional[float] = Field(None, description="The presence penalty.")
    frequency_penalty: Optional[float] = Field(None, description="The frequency penalty.")
    system_prompt_template: str = Field("You are a helpful AI assistant.", description="The system prompt template.")


class GeminiLLMConfig(BaseSchema):
    provider: Literal["gemini"] = "gemini"
    model: str = Field("gemini-1.5-flash", description="The model to use.")
    voice_id: str = Field("Prik", description="The voice ID to use.")
    temperature: float = Field(0.7, description="The temperature for sampling.")
    system_prompt_template: Optional[str] = Field(None, description="The system prompt template.")


class GroqLLMConfig(BaseSchema):
    provider: Literal["groq"] = "groq"
    model: str = Field("llama-3.1-8b-instant", description="The Groq model to use.")
    temperature: float = Field(0.7, description="Controls randomness.")
    max_completion_tokens: int = Field(default=10,description="Maximum number of tokens Groq should return.")
    system_prompt: str = Field("You are a friendly filler assistant for a llm(like hmm, okay etc ). Respond with a short acknowledgement. Max 2 words.", description="System prompt for filler LLM. This is the only source of truth.")

SLLMCONFIFG =Union[GroqLLMConfig]

LLMConfig = Union[OpenAILLMConfig, GeminiLLMConfig]


# Tool Schemas
class HangupToolConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable the hangup tool.")


class BusinessToolReference(BaseSchema):
    tool_id: str = Field(..., description="The ID of the business tool.")
    enabled: bool = Field(True, description="Enable or disable the business tool.")


class CrmToolConfig(BaseSchema):
    """CRM MCP when enabled; Pipecat CRM_MCP_URL = API base, /mcp/stream appended. Mirror of app CrmToolConfig."""

    enabled: bool = Field(False, description="Enable CRM MCP (CRM_MCP_URL base + /mcp/stream in Pipecat).")


class ToolsConfig(BaseSchema):
    hangup_tool: HangupToolConfig = Field(default_factory=HangupToolConfig)
    business_tools: List[BusinessToolReference] = Field(default_factory=list)
    crm: Optional[CrmToolConfig] = Field(
        None,
        description='CRM MCP: {"enabled": true} — Pipecat CRM_MCP_URL = API base (e.g. https://host/crm-api), /mcp/stream appended.',
    )


# Call Lifecycle Schemas
class PostCallAction(BaseSchema):
    tool_id: str = Field(..., description="The ID of the tool to execute.")


class CallLifecycleConfig(BaseSchema):
    pre_call_enrichment_enabled: bool = Field(True, description="Enable pre-call enrichment.")
    pre_call_enrichment_tool_id: Optional[str] = Field(None, description="The tool ID for pre-call enrichment.")
    post_call_actions_enabled: bool = Field(True, description="Enable post-call actions.")
    post_call_actions: List[PostCallAction] = Field(default_factory=list)


# Agent Schemas
class PipelineMode(str, Enum):
    TRADITIONAL = "traditional"
    MULTIMODAL = "multimodal"


class CustomerDetails(BaseSchema):
    name: Optional[str] = Field(None, description="The customer's name.")
    email: Optional[str] = Field(None, description="The customer's email address.")
    history: Optional[str] = Field(None, description="A summary of the customer's interaction history.")
    extra: Optional[Dict[str, Any]] = Field(None, description="Additional JSON data for custom details.")


class FirstMessageMode(str, Enum):
    SPEAK_FIRST = "speak_first"
    WAIT_FOR_USER = "wait_for_user"
    MODEL_GENERATED = "model_generated"


class SpeakFirstMessageConfig(BaseSchema):
    mode: Literal["speak_first"] = "speak_first"
    text: str = Field("Hello! I am default agent, set to answer your questions.", description="The text for the assistant to speak first.")


class WaitForUserMessageConfig(BaseSchema):
    mode: Literal["wait_for_user"] = "wait_for_user"


class ModelGeneratedMessageConfig(BaseSchema):
    mode: Literal["model_generated"] = "model_generated"
    prompt: Optional[str] = Field("Please introduce yourself to the user and ask how you can help.", description="The prompt for the model to generate the first message.")


FirstMessageConfig = Union[SpeakFirstMessageConfig, WaitForUserMessageConfig, ModelGeneratedMessageConfig]


class IdleTimeoutConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable idle timeout detection.")
    timeout_seconds: float = Field(10.0, description="Seconds of inactivity before triggering the idle handler.")
    retries: int = Field(2, description="Number of times to prompt the user before ending the call.")
    prompt_templates: List[str] = Field(default_factory=lambda: ["Are you still there?", "If you're still there, please say something or I'll have to disconnect."])


class FillerWordsConfig(BaseSchema):
    enabled: bool = Field(True, description="Enable or disable filler words for LLM delays.")
    filler_phrases: List[str] = Field(default_factory=lambda: ["Let me check that for you...", "I'll look into that right away..."])
    delay_seconds: float = Field(0.5, description="Seconds to wait before speaking the filler text.")


class OpenAISummarizationConfig(BaseSchema):
    provider: Literal["openai"] = "openai"
    model: str = Field("gpt-4o", description="The OpenAI model to use for summarization.")
    prompt_template: str = Field("You are an intelligent call analysis assistant...", description="Template for the summarization prompt.")


class GeminiSummarizationConfig(BaseSchema):
    provider: Literal["gemini"] = "gemini"
    model: str = Field("gemini-1.5-flash", description="The Gemini model to use for summarization.")
    prompt_template: str = Field("You are an intelligent call analysis assistant...", description="Template for the summarization prompt.")


SummarizationConfig = Union[OpenAISummarizationConfig, GeminiSummarizationConfig]


class ContextConfig(BaseSchema):
    enabled: bool = Field(True, description="Master switch to enable or disable all session context building.")
    include_transport_details: bool = Field(True, description="Include transport mode and connection details.")
    include_user_details: bool = Field(True, description="Include user identification details from authentication.")
    include_phone_numbers: bool = Field(True, description="Include phone numbers of participants in phone calls.")
    include_call_direction: bool = Field(True, description="Include call direction analysis for phone calls.")
    include_browser_info: bool = Field(True, description="Include browser and device information for WebRTC connections.")
    enhance_system_prompt: bool = Field(True, description="Automatically inject context information into the AI's system prompt.")
    call_lifecycle: Optional[CallLifecycleConfig] = Field(None, description="Configuration for pre-call CRM enrichment and post-call CRM actions.")


class AgentConfig(BaseSchema):
    name: Optional[str] = Field(None, description="A descriptive name for the assistant.")
    pipeline_mode: PipelineMode = Field(PipelineMode.TRADITIONAL, description="The type of pipeline to use.")
    stt: STTConfig = Field(default_factory=OpenAISTTConfig, discriminator="provider")
    tts: TTSConfig = Field(default_factory=SarvamTTSConfig, discriminator="provider")
    llm: LLMConfig = Field(default_factory=OpenAILLMConfig, discriminator="provider")
    customer_details: Optional[CustomerDetails] = Field(None, description="Details about the customer.")
    first_message: FirstMessageConfig = Field(default_factory=ModelGeneratedMessageConfig, discriminator="mode")
    report_only_initial_ttfb: bool = Field(True, description="If true, logs TTFB only once per service.")
    idle_timeout: IdleTimeoutConfig = Field(default_factory=IdleTimeoutConfig)
    filler_words: FillerWordsConfig = Field(default_factory=FillerWordsConfig)
    summarization_enabled: bool = Field(True, description="Enable or disable call summarization.")
    summarization: SummarizationConfig = Field(default_factory=OpenAISummarizationConfig, discriminator="provider")
    tools: Optional[ToolsConfig] = Field(None, description="Configuration for available tools.")
    context_config: ContextConfig = Field(default_factory=ContextConfig)
    extra_overrides: Optional[Dict[str, Any]] = Field(None, description="Extra override parameters.")
    vad: VADConfig = Field(default_factory=VADConfig)
    krisp_viva_filter: KrispVivaFilterConfig = Field(default_factory=KrispVivaFilterConfig)


def validate_agent_config_strict(config_data: Dict[str, Any]) -> AgentConfig:
    """Validate AgentConfig with strict checking (extra="forbid" behavior).
    
    This function validates an agent configuration dictionary and ensures no extra fields
    are present. Use this for API request/response validation where strict validation is required.
    
    Args:
        config_data: Dictionary containing the agent configuration
        
    Returns:
        Validated AgentConfig instance
        
    Raises:
        ValidationError: If the configuration is invalid or contains extra fields
        
    Example:
        >>> config = {"name": "My Assistant", "stt": {"provider": "openai", "model": "whisper-1"}}
        >>> validated = validate_agent_config_strict(config)
    """
    # First, validate the structure using AgentConfig (which allows extra fields)
    try:
        config = AgentConfig(**config_data)
    except ValidationError as e:
        raise e
    
    # Check for extra fields by comparing input keys with model fields
    # Get all valid field names from the model
    valid_fields = set(config.model_fields.keys())
    input_keys = set(config_data.keys())
    extra_fields = input_keys - valid_fields
    
    if extra_fields:
        # Build validation errors for extra fields
        errors = []
        for field in sorted(extra_fields):
            errors.append({
                "type": "extra_forbidden",
                "loc": (field,),
                "msg": "Extra inputs are not permitted",
                "input": config_data[field],
            })
        raise ValidationError.from_exception_data("AgentConfig", errors)
    
    return config
