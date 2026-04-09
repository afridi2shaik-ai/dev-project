# LLM Services Guide

## Overview

The Pipecat-Service provides comprehensive support for multiple LLM providers with intelligent tool management, context aggregation, and multimodal capabilities. This guide covers LLM integration architecture, provider implementations, tool registration, and advanced configuration.

## Table of Contents

1. [Supported LLM Providers](#supported-llm-providers)
2. [LLM Service Architecture](#llm-service-architecture)
3. [Tool Registration System](#tool-registration-system)
4. [Context Management](#context-management)
5. [Provider-Specific Implementation](#provider-specific-implementation)
6. [Configuration & Tuning](#configuration--tuning)
7. [Error Handling & Debugging](#error-handling--debugging)

---

## Supported LLM Providers

### OpenAI

**Status:** ✅ Fully Supported

**Models:**
- `gpt-4o` (recommended - multimodal, latest)
- `gpt-4-turbo`
- `gpt-4`
- `gpt-3.5-turbo`

**Features:**
- Full function calling support
- Context management via OpenAILLMContext
- Streaming responses
- Tool integration (hangup, warm transfer, business tools)

**Pipeline Modes Supported:**
- Traditional ✅
- Enhanced ✅
- Multimodal ❌ (Use Gemini for true multimodal)

**Setup:**
```python
OPENAI_API_KEY=sk-...  # .env configuration
```

### Google Gemini

**Status:** ✅ Fully Supported

**Models:**
- `gemini-2.0-flash-live-001` (multimodal, lowest latency)
- `gemini-2.0-flash`
- `gemini-1.5-pro`
- `gemini-1.5-flash`

**Variants:**
1. **Traditional Pipeline** - Text-based with STT/TTS
2. **Multimodal Pipeline (Live)** - Direct speech-to-speech, lowest latency

**Features:**
- Streaming responses
- Native multimodal support (Gemini Live)
- Function calling (limited compared to OpenAI)
- Language-specific optimizations

**Pipeline Modes Supported:**
- Traditional ✅
- Enhanced ✅
- Multimodal ✅ (Gemini Live only)

**Setup:**
```python
GEMINI_API_KEY=...  # .env configuration
```

### Other Supported Providers

The infrastructure is extensible for other LLM providers:

- **Anthropic Claude** - Can be integrated following provider pattern
- **Cohere** - Can be integrated following provider pattern
- **LLaMA (via Replicate/Hugging Face)** - Can be integrated
- **Custom LLM endpoints** - Support via HTTP wrapper

---

## LLM Service Architecture

### Service Creation Flow

The LLM service creation follows a provider-aware pattern:

```
AgentConfig (pipeline_mode, llm.provider)
    ↓
BaseAgent.__init__()
    ↓
[Branch on LLM Provider]
    ├─ OpenAI → create_llm_service_with_context()
    ├─ Gemini (Traditional) → create_google_text_llm_service()
    └─ Gemini (Multimodal) → create_gemini_multimodal_llm_service()
    ↓
Service initialized with messages, tools, context
    ↓
Pipeline includes LLM Service
    ↓
Ready for frame processing
```

### LLM Configuration Schema

**File:** `src/app/schemas/services/agent.py`

```python
class LLMConfig:
    """Language Model configuration"""
    
    provider: LLMProvider  # "openai", "gemini", etc.
    model: str  # "gpt-4o", "gemini-2.0-flash", etc.
    
    # Parameters
    temperature: float = 0.7        # Creativity: 0.0-2.0
    top_p: float = 1.0             # Diversity: 0.0-1.0
    max_tokens: int = 4096         # Response length
    
    # OpenAI-specific
    presence_penalty: float = 0.0   # Penalize token repetition
    frequency_penalty: float = 0.0  # Penalize frequency
    
    # System context
    system_prompt: str | None       # System message
```

### LLM Context Types

#### OpenAILLMContext

**Purpose:** Manages message history for OpenAI API

**Features:**
- Maintains list of messages with roles: "system", "user", "assistant"
- Handles function call responses
- Provides message serialization for API calls

**Usage:**
```python
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

context = OpenAILLMContext([
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"},
])
```

#### Gemini Text Context

**Purpose:** Manages message history for Gemini API (traditional mode)

**Features:**
- Similar to OpenAI but Gemini-specific format
- Handles Gemini tool calling
- Content parts management

**Usage:**
```python
from pipecat.services.google.llm import GoogleLLMService

llm = GoogleLLMService(
    api_key=settings.GEMINI_API_KEY,
    model="gemini-2.0-flash",
)
```

#### Gemini Multimodal (Live) Context

**Purpose:** Direct speech-to-speech with Gemini Live API

**Features:**
- Handles audio frames natively
- No intermediate STT/TTS
- Lowest latency (100-500ms)
- Session-based (not message-based)

**Usage:**
```python
llm = GeminiLiveLLMService(
    api_key=settings.GEMINI_API_KEY,
    model="gemini-2.0-flash-live-001",
)
```

---

## Tool Registration System

### Overview

Tools allow the LLM to take actions beyond conversation:

1. **Standard Tools** (always available)
   - Hangup
   - Warm Transfer
   - Session Context

2. **Business Tools** (configured per agent)
   - CRM integrations
   - External APIs
   - Custom business logic

### Standard Tools Registration

**File:** `src/app/services/tool_registration_service.py`

#### Hangup Tool

**Purpose:** Allow LLM to end the call

**Configuration:**
```python
class HangupToolConfig:
    enabled: bool = True
```

**Schema:**
```python
{
    "name": "hangup_call",
    "description": "Ends the current call",
    "parameters": {}
}
```

**Availability Check:**
```python
def is_hangup_enabled(tools_config: ToolsConfig | None) -> bool:
    if not tools_config or tools_config.hangup_tool is None:
        return True  # Default: enabled
    return bool(tools_config.hangup_tool.enabled)
```

#### Warm Transfer Tool

**Purpose:** Transfer call to human agent

**Configuration:**
```python
class WarmTransferConfig:
    enabled: bool
    phone_number: str  # Destination phone number
```

**Schema:**
```python
{
    "name": "warm_transfer",
    "description": "Transfer call to a human agent",
    "parameters": {
        "agent_phone": "str",
        "hold_message": "str"
    }
}
```

**Availability Check:**
```python
def is_warm_transfer_enabled(tools_config: ToolsConfig | None) -> bool:
    if not tools_config or tools_config.Warm_transfer_tool is None:
        return False
    cfg = tools_config.Warm_transfer_tool
    return bool(cfg.enabled and cfg.phone_number)
```

#### Session Context Tool

**Purpose:** Allow LLM to query session context

**Always Registered:** ✅ Yes (no configuration needed)

**Provides:**
- Caller phone number
- Session metadata
- Transport details
- User context

**Schema:**
```python
{
    "name": "get_session_context",
    "description": "Get current session information",
    "parameters": {
        "session_id": "str"
    }
}
```

### Business Tools Registration

**File:** `src/app/services/tool/business_tool_registration_service.py`

**Process:**

1. **Load Tool Configuration**
   ```python
   tool_config = await tool_service.get_tool(tool_id)
   ```

2. **Build Tool Schema**
   ```python
   schema = {
       "name": tool_config.name,
       "description": tool_config.description,
       "parameters": tool_config.build_schema()
   }
   ```

3. **Register with LLM**
   ```python
   if hasattr(llm_service, 'register_function'):
       llm_service.register_function(tool_config)
   ```

4. **Setup Execution Handler**
   ```python
   executor = BusinessToolExecutor(db, tenant_id, aiohttp_session)
   # Handler will intercept function calls and execute tools
   ```

### CRM MCP (Pipecat MCPClient)

**File:** `src/app/services/crm_mcp.py`  
**Schema:** `ToolsConfig.crm` → `CrmToolConfig` in `src/app/schemas/services/tools.py`

Registers tools from the **CRM MCP** server using Pipecat’s **`MCPClient`** ([docs](https://docs.pipecat.ai/server/utilities/mcp)). Set **`CRM_MCP_URL`** in Pipecat env to the CRM API base (e.g. `https://host/crm-api`); **`/mcp/stream`** is appended unless the value already ends with **`/stream`**.

**Assistant configuration** — nest under **`tools`**:

```json
"crm": {
  "enabled": true
}
```

**Auth:** same **`TokenProvider`** + **`tenant_id`** path as RAG (`Authorization: Bearer …`).

**Wiring:** OpenAI/LiteLLM pipelines merge MCP tool schemas in `openai_llm_service.py`; Gemini pipelines use a two-step schema + bind in `gemini_llm_service.py`.

### Tool Execution Flow

```
LLM generates function call
    ↓
Pipeline detects FunctionCallFrame
    ↓
Tool Executor validates parameters
    ↓
Executor runs tool (API call, DB query, etc.)
    ↓
Executor captures response
    ↓
Pipeline creates FunctionResultFrame
    ↓
LLM processes result in context
    ↓
LLM generates final response
    ↓
Response sent to user
```

---

## Context Management

### Message Flow

```
1. User Input
   ↓
2. STT → Transcription
   ↓
3. Context Aggregator adds: {"role": "user", "content": "..."}
   ↓
4. LLM receives message list
   ↓
5. LLM generates response
   ↓
6. Context Aggregator adds: {"role": "assistant", "content": "..."}
   ↓
7. History maintained for next turn
```

### Context Aggregator Integration

**File:** `src/app/core/observers/session_log_observer.py`

**Responsibilities:**
- Accumulates user/assistant messages
- Maintains conversation history
- Prepares context for next LLM call
- Handles function results

**Dual-Channel Architecture:**

```python
# User channel (receives user transcriptions)
context_aggregator.user()
    ↓ [adds to messages list]
    ↓ [formats as {"role": "user", "content": "..."}]

# Assistant channel (receives bot responses)
context_aggregator.assistant()
    ↓ [adds to messages list]
    ↓ [formats as {"role": "assistant", "content": "..."}]
```

### Customer Profile Injection

**When enabled in AgentConfig:**

```python
customer_profile_config: CustomerProfileConfig(
    use_in_prompt: True,  # Inject profile into system message
)
```

**Result:**
- Customer context added to initial system message
- Profile information enriches LLM understanding
- Personalized responses based on customer history

**Implementation in BaseAgent:**
```python
if self._customer_profile and use_profile_prompt:
    system_prompt = self._customer_profile_service.build_profile_context(
        self._customer_profile
    )
    self._messages.append({
        "role": "system",
        "content": system_prompt
    })
```

### System Prompt Construction

**Sources of system context:**

1. **Base System Prompt** - From AgentConfig
   ```python
   llm.system_prompt: str = "You are a helpful assistant..."
   ```

2. **Customer Profile** - If enabled
   ```python
   "Customer History: [last 3 calls], Preferences: [language, interests]"
   ```

3. **Session Context** - If enabled
   ```python
   "Transport: WebRTC, Language: en, Region: US"
   ```

4. **Business Rules** - If defined
   ```python
   "Available tools: [hangup, transfer, CRM lookup]"
   ```

---

## Provider-Specific Implementation

### OpenAI Implementation

**File:** `src/app/services/llm/openai_llm_service.py`

**Function:** `create_llm_service_with_context()`

**Process:**

```python
async def create_llm_service_with_context(
    messages: list[dict[str, str]] = None,
    model: str = "gpt-4o",
    temperature: float = 0.7,
    tools_config: ToolsConfig = None,
    agent_config: AgentConfig = None,
    aiohttp_session: aiohttp.ClientSession = None,
    db: AsyncIOMotorDatabase = None,
    tenant_id: str = None,
    agent = None,
):
    # 1. Create LLM service with API key
    llm = OpenAILLMService(
        api_key=settings.OPENAI_API_KEY,
        model=model,
        temperature=temperature,
        ...
    )
    
    # 2. Create context with initial messages
    context = OpenAILLMContext(messages or [])
    
    # 3. Register tools
    tools = await register_tools(llm, tools_config, ...)
    
    # 4. Register context with LLM
    llm.register_context(context)
    
    return llm
```

**Message Format:**
```python
[
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "What's the weather?"},
    {"role": "assistant", "content": "I'll check the weather for you"},
    {"role": "user", "content": "In San Francisco"}
]
```

**Tool Registration:**
```python
# OpenAI supports full function calling
llm.register_function(hangup_call)
llm.register_function(warm_transfer)
llm.register_function(business_tool_schema)
```

### Gemini Traditional Implementation

**File:** `src/app/services/llm/gemini_llm_service.py`

**Function:** `create_google_text_llm_service()`

**Key Differences from OpenAI:**

1. **Message Format:** Similar but with Gemini-specific handling
2. **Tool Format:** Gemini tools use different schema
3. **System Message:** Handled via message role = "system"
4. **Limitations:** Fewer function calling features than OpenAI

**Message Format:**
```python
[
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "What's the weather?"},
    {"role": "model", "content": "I'll check the weather for you"},
    # Note: Gemini uses "model" instead of "assistant"
]
```

**Implementation:**
```python
context = OpenAILLMContext(messages)  # Reuses OpenAI context format
llm = GoogleLLMService(
    api_key=settings.GEMINI_API_KEY,
    model="gemini-2.0-flash",
)
llm.register_context(context)
```

### Gemini Multimodal (Live) Implementation

**File:** `src/app/services/llm/gemini_llm_service.py`

**Function:** `create_gemini_multimodal_llm_service()`

**Unique Characteristics:**

1. **No STT/TTS Services** - Gemini handles speech natively
2. **Direct Audio Processing** - Raw audio frames input
3. **Session-Based** - Not message-based
4. **Lowest Latency** - 100-500ms typical

**Pipeline:**
```
Audio Input
    ↓ (Raw audio)
Gemini Live LLM
    ↓ (Audio output)
Audio Output
```

**Configuration:**
```python
llm = GeminiLiveLLMService(
    api_key=settings.GEMINI_API_KEY,
    model="gemini-2.0-flash-live-001",
    voice_id="Prik",  # Available voices
    system_prompt="You are a helpful assistant",
)
```

**When to Use:**
- ✅ Lowest latency requirement
- ✅ Continuous speech interaction
- ✅ Natural back-and-forth dialog
- ✅ Gemini-only deployment

**When NOT to Use:**
- ❌ Need detailed transcripts
- ❌ OpenAI-specific features required
- ❌ Need to log conversation text
- ❌ Require STT/TTS flexibility

---

## Configuration & Tuning

### Temperature & Sampling

**Temperature (Creativity):**
- `0.0` - Deterministic (same output every time)
- `0.5` - Focused, minimal creativity
- `0.7` - Balanced (default)
- `1.5` - Creative, less predictable
- `2.0` - Maximum randomness

**When to adjust:**
- Lower for customer support (consistent answers)
- Higher for creative tasks (brainstorming, content)

**Top-P (Diversity):**
- `1.0` - Full distribution
- `0.8` - More focused
- `0.5` - Very focused

### Token Limits

**max_tokens Configuration:**
```python
llm.max_tokens = 4096  # Max response length
```

**Impact:**
- Higher = Longer responses, more context used
- Lower = Faster responses, more concise
- Optimal: 1024-2048 for voice interactions

### Penalties (OpenAI only)

**Presence Penalty:**
```python
presence_penalty = 0.5  # Discourage new topics
```

**Frequency Penalty:**
```python
frequency_penalty = 0.3  # Discourage repetition
```

### Model Selection Matrix

| Use Case | OpenAI | Gemini |
|----------|--------|--------|
| **Highest Quality** | gpt-4o | gemini-1.5-pro |
| **Speed/Cost** | gpt-3.5-turbo | gemini-2.0-flash |
| **Lowest Latency** | N/A | gemini-2.0-flash-live |
| **Multimodal** | Limited | Full support |
| **Tool Calling** | Best | Good |
| **Streaming** | Yes | Yes |

---

## Error Handling & Debugging

### Common LLM Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `invalid_request_error` | Malformed messages | Check message format and context |
| `token_limit_exceeded` | Message history too long | Reduce max_tokens or limit history |
| `model_not_found` | Invalid model name | Verify model in AgentConfig |
| `auth_error` | Invalid API key | Check GEMINI_API_KEY or OPENAI_API_KEY |
| `rate_limit_error` | Too many requests | Implement exponential backoff |

### Debugging LLM Issues

**Enable Detailed Logging:**
```python
# In main.py or config
LOG_LEVEL = "DEBUG"
```

**Check LLM Logs:**
```
[LLM] Message sent: {...}
[LLM] Response received: {...}
[LLM] Tool call detected: {...}
[LLM] Context size: X messages
```

**Monitor Token Usage:**
```python
# Log in custom observer
logger.info(f"Tokens used: {response.usage.total_tokens}")
```

**Verify Context:**
```python
# Check message history format
logger.info(f"Context: {json.dumps(llm.context.messages, indent=2)}")
```

### Provider-Specific Debugging

**OpenAI:**
```
Check API key: echo $OPENAI_API_KEY
Test API: curl -H "Authorization: Bearer $KEY" https://api.openai.com/v1/models
```

**Gemini:**
```
Check API key: echo $GEMINI_API_KEY
Test multimodal: Run in pipeline_mode="multimodal"
```

---

## Summary

The LLM services architecture provides:

- **Multi-provider support** (OpenAI, Gemini, extensible)
- **Flexible tool registration** (standard and business tools)
- **Context management** (message history, customer profiles)
- **Intelligent configuration** (tunable parameters per use case)
- **Production-ready** (error handling, logging, observability)

Choose the right provider and configuration for your use case, leverage the tool system for extended capabilities, and monitor LLM behavior through logging and context inspection.

