# Session Management Guide

## Overview

Sessions represent individual conversations or interactions with the AI agent. This guide covers session lifecycle, state management, metadata handling, and the SessionContextService that aggregates context information.

## Table of Contents

1. [Session Lifecycle](#session-lifecycle)
2. [Session States](#session-states)
3. [Session Schema](#session-schema)
4. [SessionManager](#sessionmanager)
5. [SessionContextService](#sessioncontextservice)
6. [Session Metadata](#session-metadata)
7. [Best Practices](#best-practices)

---

## Session Lifecycle

### Creation to Completion

```
1. Session Creation (PREFLIGHT)
   ├─ Generate session_id
   ├─ Link to assistant configuration
   ├─ Store participant info
   ├─ Fetch assistant config from API
   ├─ Create initial log entry
   └─ Return session to caller

2. Session Initialization (IN_FLIGHT)
   ├─ Load assistant config
   ├─ Build conversation context
   ├─ Initialize LLM/STT/TTS services
   ├─ Start pipeline
   └─ Ready for user interaction

3. Active Conversation (IN_FLIGHT)
   ├─ Process user input → STT
   ├─ Generate context
   ├─ LLM reasoning
   ├─ TTS output
   ├─ Log messages & artifacts
   └─ Update session metadata

4. Session Termination
   ├─ End call (hang up)
   ├─ Finalize transcript
   ├─ Run post-call actions
   ├─ Generate summary (if enabled)
   ├─ Update session state
   └─ Archive logs

5. Session Completion (COMPLETED/ERROR)
   ├─ Final log entry
   ├─ Update end_time
   ├─ Mark final state
   └─ Session archived
```

---

## Session States

**File:** `src/app/schemas/session_schema.py`

### State Transitions

```
PREFLIGHT ─→ IN_FLIGHT ─→ COMPLETED
         ↓                ↓
         └─→ ERROR ←─────┘
         ├─→ MISSED_CALL
         ├─→ BUSY
         └─→ FAILED
```

### State Descriptions

| State | Meaning | Transition |
|-------|---------|-----------|
| **PREFLIGHT** | Session created but not started | → IN_FLIGHT when agent initializes |
| **IN_FLIGHT** | Active conversation in progress | → COMPLETED when call ends normally |
| **COMPLETED** | Call finished successfully | Terminal state |
| **ERROR** | Call failed due to error | Terminal state |
| **MISSED_CALL** | Outbound call not answered | Terminal state (telephony only) |
| **BUSY** | Recipient was busy | Terminal state (telephony only) |
| **FAILED** | Call failed for other reason | Terminal state |

### State Usage

**Check current state:**
```python
session = await session_manager.get_session(session_id)

if session.state == SessionState.IN_FLIGHT:
    # Call is active
    ...
elif session.state == SessionState.COMPLETED:
    # Call finished
    ...
```

**Update state:**
```python
await session_manager.update_session(
    session_id=session_id,
    state=SessionState.COMPLETED,
    end_time=datetime.datetime.now(datetime.timezone.utc),
)
```

---

## Session Schema

**File:** `src/app/schemas/session_schema.py`

### Session Object

```python
class Session(BaseSchema):
    # Identifiers
    session_id: str              # Unique session ID (primary key)
    agent_type: str | None       # Type of agent used
    assistant_id: str | None     # Assistant configuration ID
    
    # Configuration
    assistant_overrides: dict    # Config overrides for this session
    
    # Transport
    transport: str               # e.g., "webrtc", "plivo", "twilio"
    provider_session_id: str | None  # Provider-specific ID
    
    # Participants
    participants: list[ParticipantDetails]  # Who was involved
    created_by: UserInfo | None  # Who initiated
    
    # State
    state: SessionState          # Current state
    
    # Timing
    created_at: datetime         # Creation time
    updated_at: datetime         # Last update
    end_time: datetime | None    # When session ended
    
    # Context
    metadata: dict | None        # Custom metadata
    context_summary: dict | None # Quick reference context
```

### Example Session Document

```json
{
    "_id": "sess_abc123xyz",
    "agent_type": "vagent_pipe_cat",
    "assistant_id": "asst_001",
    "assistant_overrides": {
        "llm": {
            "temperature": 0.8
        }
    },
    "transport": "plivo",
    "provider_session_id": "call_123456",
    "participants": [
        {
            "name": "John Doe",
            "phone": "+1-555-1234",
            "email": "john@example.com"
        }
    ],
    "created_by": {
        "user_id": "user_123",
        "name": "System",
        "email": "system@example.com"
    },
    "state": "in_flight",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z",
    "end_time": null,
    "metadata": {
        "campaign": "customer_support",
        "priority": "high",
        "custom_field": "value"
    },
    "context_summary": {
        "transport_mode": "phone_call",
        "user_language": "en",
        "call_duration_seconds": 300
    }
}
```

---

## SessionManager

**File:** `src/app/managers/session_manager.py`

### Responsibilities

1. **Create sessions** - Initialize new session records
2. **Retrieve sessions** - Fetch session by ID
3. **Update sessions** - Modify session state/metadata
4. **Query sessions** - Search by various criteria
5. **Manage logs** - Store session artifacts and transcripts

### Key Methods

#### create_session()

**Purpose:** Create and initialize a new session.

**Signature:**
```python
async def create_session(
    session_id: str,
    assistant_id: str,
    assistant_overrides: dict[str, Any] | None = None,
    participants: list[ParticipantDetails] = [],
    created_by: UserInfo | None = None,
    transport: str = "pending",
    provider_session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Session:
```

**Example:**
```python
from app.managers.session_manager import SessionManager
from app.schemas.participant_schema import ParticipantDetails
from app.schemas.user_schema import UserInfo

session_manager = SessionManager(db)

session = await session_manager.create_session(
    session_id="sess_123",
    assistant_id="asst_001",
    assistant_overrides={"llm": {"temperature": 0.9}},
    participants=[
        ParticipantDetails(
            name="John Doe",
            phone="+1-555-1234",
            email="john@example.com"
        )
    ],
    created_by=UserInfo(
        user_id="user_123",
        name="System",
        email="system@example.com"
    ),
    transport="plivo",
    metadata={"campaign": "support"}
)

print(f"Session created: {session.session_id}")
print(f"State: {session.state}")  # PREFLIGHT
```

**Process:**
1. Validates assistant overrides structure
2. Creates Session object in PREFLIGHT state
3. Inserts into MongoDB
4. Fetches assistant config from external API
5. Merges with overrides
6. Stores initial log artifacts
7. Returns Session object

#### get_session()

**Purpose:** Retrieve session by ID.

**Signature:**
```python
async def get_session(session_id: str) -> Session:
```

**Example:**
```python
session = await session_manager.get_session("sess_123")

if session:
    print(f"Session state: {session.state}")
    print(f"Transport: {session.transport}")
else:
    print("Session not found")
```

#### update_session()

**Purpose:** Update session state and/or metadata.

**Signature:**
```python
async def update_session(
    session_id: str,
    state: SessionState | None = None,
    metadata: dict[str, Any] | None = None,
    context_summary: dict[str, Any] | None = None,
    end_time: datetime.datetime | None = None,
    updated_by: UserInfo | None = None,
) -> Session:
```

**Example:**
```python
# Update state to IN_FLIGHT
session = await session_manager.update_session(
    session_id="sess_123",
    state=SessionState.IN_FLIGHT,
)

# Update metadata with call duration
session = await session_manager.update_session(
    session_id="sess_123",
    metadata={"duration_seconds": 300},
    context_summary={"call_duration": 300},
)

# Mark as completed
session = await session_manager.update_session(
    session_id="sess_123",
    state=SessionState.COMPLETED,
    end_time=datetime.datetime.now(datetime.timezone.utc),
)
```

#### get_config()

**Purpose:** Get merged assistant configuration for session.

**Signature:**
```python
async def get_config(session_id: str) -> AgentConfig:
```

**Process:**
1. Check if config cached in logs
2. If not, fetch from external API
3. Merge with overrides
4. Cache in logs for future use
5. Return final config

**Example:**
```python
config = await session_manager.get_config("sess_123")

print(f"LLM Model: {config.llm.model}")
print(f"STT Provider: {config.stt.provider}")
print(f"Temperature: {config.llm.temperature}")
```

---

## SessionContextService

**File:** `src/app/services/session_context_service.py`

### Purpose

Aggregates context information from multiple sources into a unified `SessionContext` object for the LLM to understand:
- How the user is communicating (web, phone, etc.)
- Who the user is (name, email, phone)
- Session-specific information
- Transport details

### Architecture

```
Session Metadata
    ↓
Transport Details
    ├─ Mode (WebRTC, Plivo, Twilio)
    ├─ Call ID
    └─ Provider details
    ↓
User Information
    ├─ From JWT tokens
    ├─ From session participants
    └─ From auth headers
    ↓
Call Data
    ├─ Call state
    ├─ Duration
    └─ Custom metadata
    ↓
Context Config
    ├─ What to include
    └─ How to format
    ↓
SessionContext (unified object)
    ├─ session_id
    ├─ transport details
    ├─ user info
    ├─ call data
    └─ formatted context string
```

### Key Method: build_session_context()

**Signature:**
```python
async def build_session_context(
    session_id: str,
    transport_name: str,
    provider_session_id: str | None = None,
    user_details: dict[str, Any] | None = None,
    transport_metadata: dict[str, Any] | None = None,
    call_data: dict[str, Any] | None = None,
    context_config: ContextConfig | None = None,
) -> SessionContext:
```

**Example:**
```python
from app.services.session_context_service import SessionContextService

context_service = SessionContextService(db, tenant_id)

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

print(context.session_id)           # sess_123
print(context.transport_mode)       # phone
print(context.user_details)         # { name, email, phone }
print(context.formatted_context)    # "User: John Doe..."
```

### SessionContext Schema

```python
class SessionContext:
    session_id: str
    
    # Transport Information
    transport_mode: TransportMode  # "webrtc", "phone", etc.
    provider_session_id: str | None
    transport_details: TransportContextDetails
    
    # User Information
    user_details: UserContextDetails
    
    # Custom Data
    call_data: dict[str, Any]
    
    # Formatted for LLM
    formatted_context: str
```

---

## Session Metadata

### Custom Metadata

**Add custom fields:**
```python
metadata = {
    "campaign": "customer_support",
    "priority": "high",
    "customer_tier": "premium",
    "issue_category": "billing",
    "language_preference": "es",
    "previous_sessions": 5,
}

session = await session_manager.create_session(
    session_id="sess_123",
    assistant_id="asst_001",
    metadata=metadata
)
```

**Access metadata:**
```python
session = await session_manager.get_session("sess_123")

campaign = session.metadata.get("campaign")
priority = session.metadata.get("priority")
```

### Context Summary

**Quick reference context:**
```python
context_summary = {
    "transport_mode": "phone_call",
    "user_language": "en",
    "call_duration_seconds": 300,
    "transcript_length": 1250,
    "tools_called": ["crm_lookup", "payment_processing"],
    "sentiment": "positive",
}

await session_manager.update_session(
    session_id="sess_123",
    context_summary=context_summary,
)
```

**Query by context:**
```python
# Find long sessions
long_sessions = await session_manager.collection.find({
    "context_summary.call_duration_seconds": {"$gt": 600}
}).to_list(length=10)

# Find high-priority support sessions
support_sessions = await session_manager.collection.find({
    "metadata.campaign": "support",
    "metadata.priority": "high"
}).to_list(length=10)
```

---

## Best Practices

### 1. Session ID Generation

**Use the provided utility:**
```python
from app.utils.session_id_utils import generate_session_id

session_id = generate_session_id()  # sess_<random>
```

**Never:**
- Use raw UUIDs
- Use predictable sequences
- Use phone numbers as IDs

### 2. Initialization Sequence

**Correct order:**
```python
# 1. Create session (PREFLIGHT)
session = await session_manager.create_session(
    session_id=session_id,
    assistant_id=assistant_id,
    transport="plivo",
    participants=[participant],
)

# 2. Build context
context = await context_service.build_session_context(
    session_id=session_id,
    transport_name="plivo",
    ...
)

# 3. Get config
config = await session_manager.get_config(session_id)

# 4. Initialize agent
agent = BaseAgent(config=config, ...)

# 5. Update state to IN_FLIGHT
await session_manager.update_session(
    session_id=session_id,
    state=SessionState.IN_FLIGHT,
)

# 6. Start conversation
await agent.start()
```

### 3. Error Handling

**Graceful state transitions:**
```python
try:
    await agent.start()
    await session_manager.update_session(
        session_id=session_id,
        state=SessionState.IN_FLIGHT,
    )
except Exception as e:
    logger.error(f"Failed to start agent: {e}")
    await session_manager.update_session(
        session_id=session_id,
        state=SessionState.ERROR,
        metadata={"error": str(e)},
    )
    raise
```

### 4. Session Cleanup

**Always finalize:**
```python
finally:
    # Update end time
    await session_manager.update_session(
        session_id=session_id,
        state=SessionState.COMPLETED,
        end_time=datetime.datetime.now(datetime.timezone.utc),
    )
    
    # Close resources
    if agent:
        await agent.cleanup()
    
    logger.info(f"Session {session_id} completed")
```

### 5. Metadata Best Practices

**DO:**
- Use consistent key naming (snake_case)
- Store structured data (use nested objects)
- Include timestamps for events
- Log important state transitions

**DON'T:**
- Store PII directly (use references)
- Store very large objects (link instead)
- Use inconsistent schemas
- Store sensitive information unencrypted

### 6. Context Service Patterns

**Initialize once:**
```python
# In main agent setup, not per message
context_service = SessionContextService(db, tenant_id)
context = await context_service.build_session_context(...)

# Store for reuse
self._context = context
```

**Access context in messages:**
```python
# LLM can reference user/transport info
context_str = f"""
User: {self._context.user_details.name}
Transport: {self._context.transport_mode}
Session: {self._context.session_id}
"""

system_prompt += f"\n{context_str}"
```

---

## Summary

The session management system provides:

- **Session Lifecycle** - From creation through completion
- **State Management** - Track session status through states
- **SessionManager** - CRUD operations for sessions
- **SessionContextService** - Unified context aggregation
- **Metadata** - Custom and structured session data

Use sessions to:
1. Track individual conversations
2. Maintain state across interactions
3. Aggregate context for the LLM
4. Log artifacts and transcripts
5. Enable post-call actions
6. Support multi-tenancy

Follow best practices for initialization, error handling, and cleanup to ensure robust session management.

