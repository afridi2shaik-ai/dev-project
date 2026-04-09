# Context Enrichment Guide

## Overview

Context enrichment automatically enhances conversation context with external data (CRM, databases) and session information. This guide covers the CRM context enricher, session context building, language detection, and user context aggregation.

## Table of Contents

1. [CRM Context Enricher](#crm-context-enricher)
2. [Session Context Building](#session-context-building)
3. [Language Detection](#language-detection)
4. [User Context Details](#user-context-details)
5. [Patterns & Best Practices](#patterns--best-practices)

---

## CRM Context Enricher

### Purpose

Automatically fetch and inject CRM data into conversation on session start, without requiring explicit LLM tool calls.

**File:** `src/app/services/crm_context_enricher.py`

### How It Works

```
Session Started
    ↓
1. Load business tool config from DB
    ↓
2. Execute business tool (API call)
    ├─ CRM lookup by phone/email
    ├─ Return customer data
    └─ Convert to structured format
    ↓
3. Inject into context aggregator
    ├─ Add as LLM message
    ├─ Make available for system prompt
    └─ Include in conversation context
    ↓
4. LLM receives enriched context
    ├─ Customer history
    ├─ Preferences
    ├─ Account status
    └─ Previous interactions
    ↓
Personalized responses
```

### Configuration

**Setup in agent config:**
```python
agent_config = AgentConfig(
    crm_enrichment=CRMEnrichmentConfig(
        enabled=True,
        tool_id="crm_lookup",  # Business tool ID
        trigger="session_start",  # When to enrich
        async_mode=True,  # Run in background
    )
)
```

### Implementation

**Function:** `enrich_context_from_crm()`

```python
async def enrich_context_from_crm(
    session_context: SessionContext,
    context_aggregator,
    tool_id: str,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
    agent=None,
) -> None:
    """
    Fetch CRM data and inject into conversation context.
    
    Runs asynchronously without blocking call initiation.
    """
    try:
        # 1. Load business tool config
        tool_service = BusinessToolService(db, tenant_id)
        tool_config = await tool_service.get_tool(tool_id)
        
        # 2. Extract user identifier from session
        user_phone = session_context.user_details.phone
        user_email = session_context.user_details.email
        
        # 3. Build input parameters for tool
        params = {
            "phone": user_phone,
            "email": user_email,
        }
        
        # 4. Execute business tool
        executor = BusinessToolExecutor(db, tenant_id, aiohttp_session)
        result = await executor.execute(tool_id, params, agent)
        
        # 5. Inject result into context
        context_msg = {
            "role": "system",
            "content": f"Customer Context:\n{json.dumps(result, indent=2)}"
        }
        
        # Add to context aggregator
        frame = LLMMessagesAppendFrame(messages=[context_msg])
        await context_aggregator.push_frame(frame)
        
        logger.info(f"CRM enrichment complete for session {session_context.session_id}")
        
    except Exception as e:
        logger.error(f"CRM enrichment failed: {e}")
        # Gracefully degrade - continue without enrichment
```

### Usage Example

**API Call:**
```python
await enrich_context_from_crm(
    session_context=session_context,
    context_aggregator=context_aggregator,
    tool_id="crm_lookup",
    db=db,
    tenant_id=tenant_id,
    aiohttp_session=aiohttp_session,
    agent=agent,
)
```

**CRM Tool Configuration:**
```json
{
    "_id": "crm_lookup",
    "name": "CRM Lookup",
    "description": "Look up customer in CRM by phone or email",
    "api": {
        "base_url": "https://crm.example.com/api/v1",
        "endpoint": "/customers/search",
        "method": "POST"
    },
    "parameters": [
        {
            "name": "phone",
            "type": "string",
            "required": false
        },
        {
            "name": "email",
            "type": "string",
            "required": false
        }
    ]
}
```

**CRM Response:**
```json
{
    "customer_id": "cust_123",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-1234",
    "account_status": "active",
    "lifetime_value": 5000,
    "last_purchase": "2024-01-10",
    "open_tickets": 2,
    "account_created": "2020-03-15"
}
```

**LLM sees:**
```
System Message: "Customer Context:
{
  'customer_id': 'cust_123',
  'name': 'John Doe',
  'account_status': 'active',
  'lifetime_value': 5000,
  'last_purchase': '2024-01-10',
  'open_tickets': 2
}"
```

---

## Session Context Building

### Overview

`SessionContextService` builds unified context from multiple sources.

**File:** `src/app/services/session_context_service.py`

### Build Process

```python
context = await context_service.build_session_context(
    session_id="sess_123",
    transport_name="plivo",
    provider_session_id="call_456",
    user_details={
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-1234"
    },
    transport_metadata={
        "origin": "+1-555-5678",
        "direction": "inbound"
    },
    call_data={
        "duration_seconds": 45,
        "transcript_length": 250
    }
)
```

### SessionContext Object

```python
class SessionContext:
    session_id: str
    transport_mode: TransportMode  # webrtc, phone, etc.
    provider_session_id: str | None
    
    # User Information
    user_details: UserContextDetails
    
    # Transport Details
    transport_details: TransportContextDetails
    
    # Call Data
    call_data: dict[str, Any]
    
    # Formatted for LLM
    formatted_context: str
```

### Formatted Context

The `formatted_context` string is ready for injection into system prompt:

```
Session: sess_123
Transport: Phone Call (Inbound)
Caller: +1-555-1234
User: John Doe (john@example.com)
Call Duration: 45 seconds
Language Detected: English
```

---

## Language Detection

### Purpose

Auto-detect user's language and adjust STT/TTS accordingly.

**File:** `src/app/services/language_detection_service.py`

### How It Works

```
User speaks
    ↓
Audio → STT
    ↓
Transcription analyzed
    ↓
Language detection model
    ↓
Confidence score calculated
    ↓
If confident (>threshold):
    ├─ Switch TTS to user's language
    ├─ Update context language
    └─ Notify MultiTTSRouter
    ↓
Continue conversation in detected language
```

### Configuration

```python
class LanguageDetectionConfig:
    enabled: bool = True
    confidence_threshold: float = 0.7  # Min confidence
    default_language: str = "en"
    supported_languages: list[str] = ["en", "es", "fr", "hi", ...]
```

### Usage

```python
from app.services.language_detection_service import (
    get_language_detection_service,
)

# Get singleton service
lang_service = get_language_detection_service(
    default_language="en",
    confidence_threshold=0.8
)

# Subscribe to language changes
lang_service.subscribe_to_language_changes(
    callback=lambda new_lang: logger.info(f"Language changed to {new_lang}")
)

# Detect from text
detected_lang, confidence = lang_service.detect_language("Hola, ¿cómo estás?")
print(f"Detected: {detected_lang} (confidence: {confidence})")
```

### With MultiTTSRouter

```python
# See CUSTOM_PROCESSORS_GUIDE.md for details
router = MultiTTSRouter(
    tts_services={
        "en": elevenlabs_en,
        "es": sarvam_es,
        "fr": elevenlabs_fr,
    },
    language_detection_service=lang_service,
)
```

---

## User Context Details

### UserContextDetails Schema

```python
class UserContextDetails:
    user_id: str | None
    name: str | None
    email: str | None
    phone: str | None
    timezone: str | None
    preferences: dict[str, Any]
```

### Extraction

**From JWT token:**
```python
current_user = get_current_user(request)
user_details = {
    "user_id": current_user.get("sub"),
    "name": current_user.get("name"),
    "email": current_user.get("email"),
}
```

**From session participants:**
```python
if session.participants:
    participant = session.participants[0]
    user_details = {
        "user_id": participant.user_id,
        "name": participant.name,
        "email": participant.email,
        "phone": participant.phone,
    }
```

**Merged into context:**
```python
context = await context_service.build_session_context(
    session_id=session_id,
    user_details=user_details,
)

# Access in LLM
print(context.user_details.name)  # "John Doe"
print(context.user_details.email)  # "john@example.com"
```

---

## Patterns & Best Practices

### 1. CRM Enrichment Pattern

**Recommended flow:**
```python
async def initialize_agent(session_id, assistant_id):
    # 1. Create session
    session = await session_manager.create_session(...)
    
    # 2. Build context
    context = await context_service.build_session_context(...)
    
    # 3. Enrich with CRM in background
    asyncio.create_task(
        enrich_context_from_crm(
            context,
            context_aggregator,
            tool_id="crm_lookup",
            ...
        )
    )
    
    # 4. Start conversation (doesn't wait for enrichment)
    await agent.start()
    
    # LLM gets enriched context within 1-2 seconds
```

### 2. Error Handling

**Graceful degradation:**
```python
try:
    await enrich_context_from_crm(...)
except CRMError as e:
    logger.warning(f"CRM enrichment failed: {e}")
    # Continue without CRM data
    # LLM still has session context
except Exception as e:
    logger.error(f"Unexpected enrichment error: {e}")
    # Log error but don't break conversation
```

### 3. Language Handling

**Consistent language usage:**
```python
# Set language in config
context = await context_service.build_session_context(
    ...
    language="es",  # Spanish
)

# STT detects user's language
lang_service.detect_language(transcription)

# TTS switches to detected language
await router.on_language_change("es")

# Update context
await session_manager.update_session(
    session_id,
    context_summary={"language": "es"}
)
```

### 4. Context in System Prompt

**Inject formatted context:**
```python
# Get context
context = await context_service.build_session_context(...)

# Add to system prompt
system_prompt = f"""You are a helpful customer support agent.

{context.formatted_context}

Be personalized and professional."""

# Include in LLM messages
messages.append({
    "role": "system",
    "content": system_prompt
})
```

### 5. Performance Optimization

**Parallel enrichment:**
```python
# Don't wait for CRM during initialization
async def init_agent():
    session = await session_manager.create_session(...)
    context = await context_service.build_session_context(...)
    
    # Start both in parallel
    crm_task = asyncio.create_task(enrich_context_from_crm(...))
    lang_task = asyncio.create_task(detect_language(...))
    
    # Start agent immediately
    await agent.start()
    
    # Wait for enrichments in background
    await asyncio.gather(crm_task, lang_task)
```

---

## Summary

Context enrichment provides:

- **CRM Context Enricher** - Auto-inject customer data
- **Session Context Service** - Unified context aggregation
- **Language Detection** - Auto-detect and adapt language
- **User Context** - Track user information
- **Graceful Degradation** - Continue if enrichment fails

Use for:
1. Personalizing responses with customer history
2. Building unified context from multiple sources
3. Supporting multilingual conversations
4. Tracking user information
5. Improving LLM decision making

