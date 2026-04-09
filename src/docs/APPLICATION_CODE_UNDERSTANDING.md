# Application Code Understanding - Knowledge Base

This document summarizes your application architecture and how the system prompt structured implementation will integrate.

---

## Current System Architecture Overview

Your application follows **Domain-Driven Design (DDD)** principles with four distinct layers:

### 1. **API Layer** (`src/app/api/`)

**Entry points for external interactions:**
- `pipecat_api.py` - WebRTC connections (offers/answers)
- `plivo_api.py` - Plivo telephony (inbound/outbound calls, WebSocket voice)
- `twilio_api.py` - Twilio telephony (similar to Plivo)
- `chat_api.py` - WebSocket text-based chat
- `assistant_api.py` - **DEPRECATED** (local CRUD removed; uses external Assistant API)

**Flow:**
1. Request arrives at an endpoint
2. Endpoint fetches session config via `SessionManager.get_and_consume_config()`
3. Creates `BaseAgent` with `AgentConfig`
4. Launches transport service (WebRTCService, PlivoService, etc.)

### 2. **Application Layer** (`src/app/agents/`)

**Core orchestrator: `BaseAgent` class**

Responsibilities:
- Initializes STT/LLM/TTS services
- Builds session context (customer details, call direction, etc.)
- Creates LLM messages list with system prompt
- Manages agent lifecycle during call

**Key method: `_create_llm_and_context()`**
- Retrieves `system_prompt_template` from `AgentConfig.llm.system_prompt_template`
- Appends customer details and session context to the prompt
- Creates LLM service with final compiled prompt

### 3. **Domain/Business Layer** (`src/app/tools/`)

- `hangup_tool.py` - Terminate calls
- `warm_transfer_tool.py` - Transfer calls to agents
- `call_scheduler_tool.py` - Schedule callbacks
- `session_context_tool.py` - Session context access

### 4. **Infrastructure Layer** (`src/app/services/`)

**Key services for system prompt:**
- `llm/` - LLM service factories (OpenAI, Gemini, Google)
- `stt/` - Speech-to-text providers
- `tts/` - Text-to-speech providers
- `tool_registration_service.py` - Registers callable tools
- `session_context_service.py` - Builds session context for prompt injection
- `customer_profile_service.py` - Resolves customer profiles
- `assistant_api_client.py` - Fetches assistant config from external API

---

## Configuration Data Flow

### Where Agent Config Comes From

```
External Assistant API
    ↓
AssistantAPIClient.get_config(assistant_id)
    ↓
SessionManager.create_session() merges:
  - base_config (from external API)
  - assistant_overrides (from request)
    ↓
Session document stores overrides
    ↓
Later: WebRTC/Plivo/Twilio request
    ↓
SessionManager.get_and_consume_config()
  - Fetches base config from external API again
  - Merges with stored overrides
  - Returns AgentConfig
    ↓
BaseAgent.__init__(agent_config=...)
    ↓
BaseAgent.get_services() calls _create_llm_and_context()
    ↓
Retrieves system_prompt_template and uses it
```

### Current AgentConfig Structure

**File:** `src/app/schemas/services/agent.py`

```
AgentConfig
├── name: str | None
├── pipeline_mode: PipelineMode ("traditional" | "multimodal" | "text")
├── stt: STTConfig (OpenAI | Google | Deepgram | etc.)
├── tts: TTSConfig (Sarvam | ElevenLabs | OpenAI | etc.)
├── llm: LLMConfig (OpenAI | Gemini)
│   ├── provider: "openai" | "gemini"
│   ├── model: str
│   ├── temperature: float | None
│   ├── system_prompt_template: str ◄─── TRUTH FOR RUNTIME
│   └── ...other params...
├── customer_details: CustomerDetails | None
├── first_message: FirstMessageConfig (speak_first | wait_for_user | model_generated)
├── idle_timeout: IdleTimeoutConfig
├── filler_words: FillerWordsConfig
├── summarization: SummarizationConfig (OpenAI | Gemini)
├── tools: ToolsConfig | None
├── context_config: ContextConfig
│   ├── enabled: bool
│   ├── include_transport_details: bool
│   ├── include_user_details: bool
│   ├── enhance_system_prompt: bool ◄─── Controls if context is added to prompt
│   └── ...more fields...
├── customer_profile_config: CustomerProfileConfig
│   ├── use_in_prompt: bool ◄─── Controls if profile is added to prompt
│   └── ...more fields...
└── ...other configs...
```

**What we're adding:**
```
AgentConfig
├── ... (all existing fields)
├── system_prompt_structured: SystemPromptStructured | None ◄─── NEW!
│   ├── enabled: bool
│   ├── sections: SystemPromptSections
│   │   ├── role: str
│   │   ├── primary_objectives: list[str]
│   │   ├── communication_style: str
│   │   ├── conversational_flow: str
│   │   ├── guardrails: list[str]
│   │   ├── faqs: list[FAQPair]
│   │   ├── closing_termination: str
│   │   └── final_output_rules: str
│   └── custom_sections: dict[str, str] | None
└── ... (existing fields)
```

---

## System Prompt Flow (Current + New)

### Current Flow (Before Implementation)

1. External API stores `assistant.config.llm.system_prompt_template` = **single string**
2. `SessionManager` fetches config, stores in session
3. `BaseAgent._create_llm_and_context()` reads `system_prompt_template`
4. Appends customer_details if available
5. Appends session context if enabled + available
6. Creates LLM with final compiled prompt

### New Flow (After Implementation)

1. **External API now stores TWO things in assistant.config:**
   - `system_prompt_structured` = **structured sections + custom**
   - `llm.system_prompt_template` = **compiled final string (truth)**

2. `SessionManager` fetches config (same as before)

3. **NEW: System Prompt Compiler Service** runs when admin updates assistant:
   - Reads `system_prompt_structured`
   - Validates all mandatory sections present
   - Checks termination rule is present
   - Renders into formatted string
   - Stores into `llm.system_prompt_template` (updates external API)

4. `BaseAgent._create_llm_and_context()` still does the same:
   - Reads `system_prompt_template` (now pre-compiled)
   - Appends customer_details / session context
   - Creates LLM

**Key point:** Runtime code (`BaseAgent`, pipeline, etc.) **stays unchanged**. All rendering happens at assistant config time.

---

## Key Files for System Prompt Implementation

### Schema Files (Will need updates)

| File | Purpose | Change |
|------|---------|--------|
| `src/app/schemas/services/llm.py` | LLM configs | ✓ Add `system_prompt_structured` field |
| `src/app/schemas/services/agent.py` | Agent config | ✓ Add `system_prompt_structured` field |
| `src/app/schemas/assistant_api_schema.py` | API response types | Consider if needed |

### Service Files (Will need new files)

| File | Purpose |
|------|---------|
| `src/app/services/system_prompt_compiler_service.py` | **NEW** - Renders structured → string |
| `src/app/services/system_prompt_validator_service.py` | **NEW** - Validates sections + rules |

### Manager Files (May need updates)

| File | Purpose |
|------|---------|
| `src/app/managers/session_manager.py` | May need to hook compiler on config updates |

### Config Merge Files (Already handle overrides)

| File | Purpose | Status |
|------|---------|--------|
| `src/app/utils/config_merge_utils.py` | Deep merge, discriminator handling | ✓ Existing (handles dicts well) |

---

## Key Integration Points

### 1. Where System Prompt Is Read

**File:** `src/app/agents/base_agent.py` (lines 107-134)

```python
async def _create_llm_and_context(self):
    if isinstance(self.config.llm, OpenAILLMConfig):
        system_prompt = self.config.llm.system_prompt_template  # ◄─── HERE
        if self.customer_details:
            # Append customer details
            system_prompt += f" The user's name is {self.customer_details.name}."
        
        # Append session context if enabled
        if self._session_context and self.config.context_config.enhance_system_prompt:
            context_info = context_service.format_system_prompt_context(...)
            system_prompt = f"{system_prompt}\n\n{context_info}"
        
        self._messages = [{"role": "system", "content": system_prompt}]
        # ... create LLM service with messages ...
```

**Status:** ✓ No changes needed here. We just ensure `system_prompt_template` is pre-compiled.

### 2. Where System Prompt Is Compiled

**NEW Location:** System Prompt Compiler Service (to be created)

This service will:
- Accept `SystemPromptStructured` dict
- Apply override mode (partial_update / append / full_update)
- Validate mandatory sections
- Render to formatted string
- Return both structured + compiled

**Trigger points:**
- When external Assistant API is called to create/update assistant
- When configuration is merged
- On-demand validation endpoint

### 3. Config Merge Logic

**File:** `src/app/utils/config_merge_utils.py` (lines 187-253)

Already has `merge_configs()` function that:
- Takes base `AgentConfig` + override dict
- Deep merges recursively
- Validates final result

**Status:** ✓ This will work for `system_prompt_structured` as-is (it's just a dict).

---

## Update Modes (Already Designed)

From `STRUCTURED_SYSTEM_PROMPT.md`:

### partial_update
- Merge override sections into existing structured sections
- Only update fields that are provided
- Example: Change only `role` section, keep others

### append
- Concatenate custom_sections with existing
- Useful for adding contextual/tenant-specific sections
- Example: Add company-specific guidelines

### full_update
- Replace entire `system_prompt_structured` with new one
- Validate all mandatory sections present
- Example: Completely new prompt template for new campaign

---

## LLM Provider Compatibility

### OpenAI (Priority 1)
- ✓ `system_prompt_template` field exists in schema
- ✓ Supported, compile to `OpenAILLMConfig.system_prompt_template`

### Gemini (Priority 2)
- ⚠️ Schema has **no** `system_prompt_template` field
- Gemini uses `model_id` + `voice_id` for voice agent config
- Currently system prompt is hardcoded as: `"You are a friendly AI assistant."`
- **Decision:** Phase 1 supports OpenAI only; Gemini support in Phase 2

---

## Implementation Roadmap

### Phase 1: Schema + Compiler

1. Add `SystemPromptSections` Pydantic schema
2. Add `SystemPromptStructured` Pydantic schema
3. Add field to `OpenAILLMConfig.system_prompt_structured` (optional)
4. Add field to `AgentConfig.system_prompt_structured` (optional, matches LLM provider)
5. Create `SystemPromptCompilerService` with rendering logic
6. Create `SystemPromptValidatorService` with validation rules
7. Update `merge_configs()` to handle structured prompt override modes

### Phase 2: API Integration

1. Update `/validate` endpoint to compile structured prompt
2. Add compiler hook to external API response handling
3. Create `/compile` endpoint for on-demand testing
4. Add structured prompt to session storage (optional)

### Phase 3: Testing + Docs

1. Unit tests for compiler logic
2. Integration tests for override modes
3. API contract tests
4. Update API documentation

---

## Next Steps (For Your Next Message)

When you're ready, you can say:
- **"Create the system prompt implementation"** → I'll build schemas + compiler service
- **"Show me the compiler logic"** → I'll design the rendering algorithm
- **"Build the validation service"** → I'll create validation rules
- **"Integrate into existing code"** → I'll add hooks to current services

---

## Quick Reference: Where Each Layer Fits

```
External Assistant API (managed elsewhere)
  ├─ Stores: system_prompt_structured + llm.system_prompt_template
  └─ Calls: Your validation/compilation endpoints (to be built)
       │
       └─→ SessionManager (gets config)
            └─→ BaseAgent (initializes with config)
                └─→ BaseAgent._create_llm_and_context()
                    └─→ Uses system_prompt_template (already compiled)
                        └─→ LLM Service (receives final prompt)
```

---

## Summary

Your application is clean and well-architected. The system prompt structured implementation will:
- **NOT touch runtime code** (API layer stays the same)
- **Add compilation layer** between config storage and LLM usage
- **Support flexible override modes** (partial/append/full)
- **Maintain backward compatibility** (existing monolithic prompts still work)
- **Integrate seamlessly** with existing session/config management

Ready for next phase! 🚀

