# Advanced Pipeline Architecture Guide

## Overview

The Pipecat-Service uses a sophisticated pipeline architecture to orchestrate real-time voice conversations. This document provides a deep dive into the three pipeline modes, processor chains, frame flow, and advanced configuration options.

## Table of Contents

1. [Pipeline Modes](#pipeline-modes)
2. [Pipeline Builders](#pipeline-builders)
3. [Processor Chain Architecture](#processor-chain-architecture)
4. [Frame Flow & Processing](#frame-flow--processing)
5. [Advanced Configuration](#advanced-configuration)
6. [Performance Optimization](#performance-optimization)

---

## Pipeline Modes

The application supports three distinct pipeline architectures, each optimized for different use cases:

### 1. **Traditional Pipeline** (STT → LLM → TTS)

**Best for:** Most voice AI applications with separate speech recognition and generation.

**Characteristics:**
- Full transcription control via dedicated STT service
- Independent TTS for flexible voice synthesis
- Complete conversation history available for context
- Maximum latency due to sequential processing

**When to use:**
- Real-time customer support
- Voice IVR systems
- Conversation-heavy applications
- When you need detailed transcripts

**Architecture:**
```
User Input (Audio)
    ↓
Transport Input
    ↓
RTVI Processor
    ↓
STT Service (Speech-to-Text)
    ↓
STT Mute Filter (optional, for speak-first)
    ↓
Transcription Filter (removes empty STT results)
    ↓
Transcript Processor (user channel)
    ↓
Context Aggregator (user channel)
    ↓
Filler Words Processor (optional, keeps user engaged)
    ↓
LLM Service (Language Model)
    ↓
User Idle Processor
    ↓
Transcript Processor (assistant channel)
    ↓
Transport Output
    ↓
Audio Buffer Processor
    ↓
Context Aggregator (assistant channel)
    ↓
User Audio Output
```

**Code Location:** `src/app/core/pipeline_builder/traditional.py`

### 2. **Enhanced Pipeline** (STT → LLM → TTS with Advanced Controls)

**Best for:** Applications requiring fine-grained control over audio processing, muting, and processor customization.

**Characteristics:**
- All features of Traditional mode
- Advanced STT mute strategies (mute during function calls, until first bot response)
- Configurable processor providers
- Intelligent transcription filtering
- Support for custom audio processors

**When to use:**
- High-quality customer interactions
- Complex dialog systems
- When you need precise control over when STT is active
- Speak-first scenarios (bot initiates conversation)

**Unique Features:**
- **STT Mute Filter:** Prevents user input transcription during bot speech or function calls
- **Transcription Filter:** Removes empty STT frames before they reach the LLM
- **RTVI Processor:** Real-time video input processing

**Code Location:** `src/app/core/pipeline_builder/enhanced.py`

### 3. **Multimodal Pipeline** (Speech-to-Speech with Gemini Live)

**Best for:** Low-latency, end-to-end speech interactions using Gemini's live API.

**Characteristics:**
- Direct audio input-to-audio output
- No intermediate STT or TTS services
- Gemini handles speech encoding/decoding natively
- Lowest latency (100-500ms typical)
- No transcript generation during call

**When to use:**
- Ultra-low-latency requirements
- Natural, continuous speech flows
- When using Gemini Live API exclusively
- Real-time interactive applications

**Architecture:**
```
User Audio Input
    ↓
Transport Input
    ↓
RTVI Processor
    ↓
Transcript Processor (user channel)
    ↓
Context Aggregator (user channel)
    ↓
Gemini Live LLM Service (handles speech natively)
    ↓
Transcript Processor (assistant channel)
    ↓
Transport Output
    ↓
Audio Buffer Processor
    ↓
Context Aggregator (assistant channel)
    ↓
User Audio Output
```

**Code Location:** `src/app/core/pipeline_builder/multimodal.py`

---

## Pipeline Builders

### Location & API

All pipeline builders are in `src/app/core/pipeline_builder/` and follow a consistent interface:

```python
def build_*_pipeline(
    transport: BaseTransport,
    stt_service,                    # Speech-to-Text (None for multimodal)
    llm_service,                    # Language Model
    tts_service,                    # Text-to-Speech (None for multimodal)
    context_aggregator,             # Context management
    agent_config: AgentConfig,      # Full configuration
    transcript_processor,           # Transcript handling
    hangup_observer=None,          # Optional observer
) -> tuple[Pipeline, AudioBufferProcessor]:
```

### Traditional Builder

**File:** `src/app/core/pipeline_builder/traditional.py`

**Returns:** Tuple of (Pipeline, AudioBufferProcessor)

**Key Responsibilities:**
1. Creates the frame processor chain
2. Injects STT mute filter if speak-first mode is enabled
3. Adds transcription filter to prevent empty STT frames
4. Configures filler words if enabled
5. Sets up idle timeout handling

**Example Usage:**
```python
pipeline, audio_buffer = build_traditional_pipeline(
    transport=transport,
    stt_service=stt_service,
    llm_service=llm_service,
    tts_service=tts_service,
    context_aggregator=context_aggregator,
    agent_config=agent_config,
    transcript_processor=transcript_processor,
)
```

### Enhanced Builder

**File:** `src/app/core/pipeline_builder/enhanced.py`

**Enhancements over Traditional:**
- STT Mute Filter with multiple strategies
- Customizable processor providers via AgentConfig
- Better error handling and logging

**STT Mute Strategies:**
1. `MUTE_UNTIL_FIRST_BOT_COMPLETE` - Prevent interruptions during first bot speech
2. `FUNCTION_CALL` - Mute during tool execution
3. `ALWAYS_MUTE` - Continuous muting

### Multimodal Builder

**File:** `src/app/core/pipeline_builder/multimodal.py`

**Minimal Pipeline:**
- No STT/TTS services (Gemini Live handles it)
- Simplest processor chain
- Fastest execution path

---

## Processor Chain Architecture

### Key Processors

#### 1. **RTVI Processor** (Real-Time Video Input)

**Purpose:** Handles real-time video input configuration for multimodal applications.

**Position:** First processor in all pipelines (after transport input)

**Configuration:**
```python
rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
```

#### 2. **STT Service**

**Position:** 2nd processor in Traditional & Enhanced modes

**Responsibilities:**
- Converts user audio to text
- Sends transcription updates
- Respects mute filters

**Supported Providers:**
- Deepgram (fastest, most accurate)
- OpenAI (integrated with LLM)
- Google Cloud STT
- ElevenLabs
- Cartesia
- Sarvam

#### 3. **STT Mute Filter** (Optional, Speak-First Mode)

**Position:** Immediately after STT service (if enabled)

**Purpose:** Prevents STT transcription during:
- First bot speech response
- Active function calls
- Custom mute triggers

**Code:** `src/app/core/pipeline_builder/mute_utils.py`

```python
def add_first_speech_mute_if_needed(processors, agent_config, stt_enabled=True):
    """Conditionally adds STT mute filter for speak-first flows."""
```

#### 4. **Transcription Filter**

**Purpose:** Removes empty STT frames before they reach the LLM

**Why it matters:** Prevents "empty" transcriptions from polluting conversation history

**Implementation:**
```python
class TranscriptionFilter(FrameProcessor):
    """Filters out empty transcriptions that can cause LLM confusion."""
```

#### 5. **Transcript Processor**

**Position:** After transcription, in dual channels (user & assistant)

**Role:** Routes transcriptions to appropriate channels:
- User channel: Captures user speech
- Assistant channel: Captures bot responses

**Usage:**
```python
transcript_processor.user()      # User speech channel
transcript_processor.assistant() # Assistant response channel
```

#### 6. **Context Aggregator**

**Position:** After transcript processor, dual channels

**Responsibilities:**
- Aggregates user and assistant messages
- Maintains conversation context
- Prepares LLM input
- Updates session metadata

**Dual Channel:**
```python
context_aggregator.user()       # Processes user context
context_aggregator.assistant()  # Processes assistant context
```

#### 7. **Filler Words Processor** (Optional)

**Position:** After context aggregator, before LLM

**Purpose:** Keeps user engaged during long processing delays

**Features:**
- Groq-powered small talk generation
- Configurable delay thresholds
- Language detection aware

**Configuration:**
```python
FillerWordsConfig(
    enabled: bool = False,
    silence_threshold_ms: int = 2000,
    groq_enabled: bool = False,
    groq_model: str = "mixtral-8x7b-32768",
)
```

#### 8. **LLM Service**

**Position:** Center of pipeline

**Responsibilities:**
- Process conversation context
- Generate responses
- Execute function/tool calls
- Manage system prompts and rules

**Supported Models:**
- OpenAI (GPT-4o, GPT-4 Turbo)
- Gemini (Traditional & Live multimodal)
- Custom LLM implementations

#### 9. **User Idle Processor**

**Position:** After LLM, before TTS output

**Purpose:** Detects when user is idle and triggers:
- Timeout messages
- Session cleanup
- Engagement prompts

**Configuration:**
```python
IdleTimeoutConfig(
    idle_timeout_seconds: int = 60,
    idle_messages: list[str] = [],
    should_hangup: bool = False,
)
```

#### 10. **Transport Output**

**Position:** Sends audio back to user

**Role:** Serializes and transmits assistant audio/responses

#### 11. **Audio Buffer Processor**

**Position:** Last processor

**Purpose:** Buffers audio for post-call analysis and logging

---

## Frame Flow & Processing

### Understanding Frames

Pipecat uses a **frame-based architecture** where data flows through processors as discrete frames:

**Common Frame Types:**

```python
# Audio Frames
AudioRawFrame           # Raw PCM audio data
AudioFrame             # Processed audio

# Text Frames
TranscriptionFrame     # User speech → text
LLMTextFrame          # LLM text output
TTSSpeakFrame         # Text to synthesize

# Control Frames
StartFrame            # Pipeline startup
EndFrame              # Pipeline shutdown
CancelFrame           # Cancel current operation

# Context Frames
LLMMessagesAppendFrame      # Add messages to LLM
LLMContextAggregatorFrame   # Context aggregation

# Tool/Function Frames
FunctionCallFrame     # Request to execute tool
FunctionResultFrame   # Tool execution result
```

### Frame Direction

Frames flow in two directions:

**Downstream (→):**
- Input → STT → LLM → TTS → Output
- User input flows through pipeline

**Upstream (←):**
- Responses flow back through pipeline
- Context updates propagate
- Errors bubble up

### Processing Example

```
User speaks: "What's the weather?"
    ↓ (AudioRawFrame)
STT Service
    ↓ (TranscriptionFrame: "What's the weather?")
Context Aggregator
    ↓ (LLMMessagesAppendFrame)
LLM Service
    ↓ (LLMTextFrame: "The weather is...")
TTS Service
    ↓ (AudioFrame)
Transport Output
    ↓ (TTSSpeakFrame)
User hears response
```

---

## Advanced Configuration

### AgentConfig Pipeline Settings

**File:** `src/app/schemas/services/agent.py`

```python
class AgentConfig:
    """Main configuration for agent behavior"""
    
    # Pipeline mode selection
    pipeline_mode: PipelineMode = "traditional"  # or "enhanced", "multimodal"
    
    # Speech-first vs. speak-first
    first_message: FirstMessageConfig
    
    # STT Configuration
    stt: STTConfig = Field(default_factory=STTConfig)
    
    # TTS Configuration
    tts: TTSConfig = Field(default_factory=TTSConfig)
    
    # LLM Configuration
    llm: LLMConfig = Field(default_factory=LLMConfig)
    
    # Filler Words (keep user engaged)
    filler_words: FillerWordsConfig = Field(default_factory=FillerWordsConfig)
    
    # Idle Timeout Handling
    idle_timeout: IdleTimeoutConfig = Field(default_factory=IdleTimeoutConfig)
    
    # Context Building
    context: ContextConfig = Field(default_factory=ContextConfig)
    
    # Customer Profile Integration
    customer_profile_config: CustomerProfileConfig | None = None
    
    # Business Tools
    tools_config: ToolsConfig | None = None
    
    # Call Summarization
    summarization_config: SummarizationConfig | None = None
```

### Pipeline Mode Selection

**In AgentConfig:**
```python
pipeline_mode: Literal["traditional", "enhanced", "multimodal"]
```

**How it's used in BaseAgent:**
```python
if self.config.pipeline_mode == "multimodal":
    pipeline, audio_buffer = build_multimodal_pipeline(...)
elif self.config.pipeline_mode == "enhanced":
    pipeline, audio_buffer = build_enhanced_pipeline(...)
else:  # default: traditional
    pipeline, audio_buffer = build_traditional_pipeline(...)
```

### Speak-First Configuration

**Purpose:** Bot initiates conversation without waiting for user input.

**Configuration:**
```python
class SpeakFirstMessageConfig:
    """Bot initiates with a first message"""
    content: str  # Message to speak first
    language: str = "en"
```

**Effect on Pipeline:**
1. STT is automatically muted until bot finishes first message
2. Prevents immediate user interruption
3. Uses STT Mute Filter with `MUTE_UNTIL_FIRST_BOT_COMPLETE` strategy

---

## Performance Optimization

### 1. **Pipeline Mode Selection**

| Mode | Latency | Quality | Use Case |
|------|---------|---------|----------|
| Multimodal | 100-500ms | High | Ultra-low latency |
| Enhanced | 500-1000ms | Very High | Quality + control |
| Traditional | 1000-2000ms | Excellent | Standard voice AI |

### 2. **Processor-Level Optimization**

**Disable Unnecessary Processors:**
```python
filler_words: FillerWordsConfig(enabled=False)  # Don't add engagement filler
idle_timeout: IdleTimeoutConfig(idle_timeout_seconds=0)  # Disable idle detection
```

**Pre-allocate Resources:**
```python
# Use audio buffer pre-allocation in production
audiobuffer = AudioBufferProcessor()
```

### 3. **Context Aggregator Tuning**

**Limit Message History:**
```python
context: ContextConfig(
    max_messages: 50  # Prevent unbounded context growth
)
```

### 4. **STT/TTS Provider Selection**

**For lowest latency:**
- STT: Deepgram (streaming-optimized)
- TTS: Cartesia or ElevenLabs (lowest latency)

**For best quality:**
- STT: Google Cloud (most accurate)
- TTS: ElevenLabs (most natural)

### 5. **Network Optimization**

**WebSocket Frame Size:**
- Smaller frames = Lower latency but more overhead
- Larger frames = Lower overhead but higher latency
- Optimal: 512-1024 bytes

**Transcription Update Frequency:**
- More frequent = Better UX but more CPU
- Less frequent = Lower CPU but less responsive
- Optimal: Update on silence/clause boundaries

---

## Debugging Pipeline Issues

### Enable Pipeline Logging

**In AgentConfig:**
```python
LOG_LEVEL = "DEBUG"  # Enable detailed logging
```

**Check logs for:**
```
[Pipeline] Frame flow
[STT] Transcription updates
[LLM] Message processing
[TTS] Audio synthesis
[Transport] I/O operations
```

### Monitor Frame Flow

**Add logging to custom processors:**
```python
async def process_frame(self, frame, direction):
    if isinstance(frame, AudioRawFrame):
        logger.info(f"Received {len(frame.audio)} bytes of audio")
    await super().process_frame(frame, direction)
```

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| High latency | Large message history | Limit context window |
| Missing transcriptions | STT mute filter too aggressive | Adjust mute strategy |
| LLM timeouts | Slow processor chain | Use multimodal mode |
| Audio dropout | Transport buffer issue | Increase buffer size |
| Memory leak | Frame queue overflow | Monitor processor queue depth |

---

## Summary

The Pipecat pipeline architecture provides:

- **Three optimized modes** for different use cases
- **Flexible processor chain** for customization
- **Frame-based data flow** for real-time processing
- **Advanced configuration** for fine-tuning behavior
- **Extensibility** for custom processors and providers

Choose the right pipeline mode and configure processors based on your application's requirements for latency, quality, and complexity.

