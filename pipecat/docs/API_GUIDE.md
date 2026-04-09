# API Guide

> 📡 **Complete API reference** • All endpoints and protocols

## Overview

The Pipecat-Service provides a comprehensive REST API for managing voice AI agents, sessions, customer profiles, and business tools. The API follows RESTful conventions with JSON request/response formats and uses Bearer token authentication.

## Base Information

**Base URL**: `https://api.example.com/api/v1`

**Authentication**: Bearer Token in `Authorization` header

```
Authorization: Bearer {your-api-token}
```

**Response Format**: All responses are JSON

```json
{
    "status": "success",
    "data": {},
    "error": null
}
```

**Tenant Isolation**: Operations are scoped to the authenticated tenant

## API Structure

```mermaid
graph TB
    subgraph Sessions["Session Management"]
        POST_sessions["POST /sessions<br/>(Create)"]
        GET_sessions["GET /sessions<br/>(List)"]
        GET_session["GET /sessions/{id}<br/>(Get)"]
        POST_end["POST /sessions/{id}/end<br/>(End)"]
    end
    
    subgraph WebRTC["WebRTC"]
        POST_offer["POST /offer<br/>(WebRTC SDP)"]
    end
    
    subgraph Profiles["Customer Profiles"]
        POST_profile["POST /customer-profiles<br/>(Create)"]
        GET_profile["GET /customer-profiles/{id}<br/>(Get)"]
        PUT_profile["PUT /customer-profiles/{id}<br/>(Update)"]
        GET_search["GET /customer-profiles/search<br/>(Search)"]
    end
    
    subgraph Tools["Business Tools"]
        POST_tool["POST /business-tools<br/>(Create)"]
        GET_tool["GET /business-tools/{id}<br/>(Get)"]
        PUT_tool["PUT /business-tools/{id}<br/>(Update)"]
        POST_test["POST /business-tools/{id}/test<br/>(Test)"]
    end
    
    subgraph Logs["Logs & Data"]
        GET_logs["GET /logs<br/>(List)"]
        GET_artifacts["GET /artifacts<br/>(List)"]
    end
```

## Error Handling

### Standard Error Response

```json
{
    "status": "error",
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request format",
        "details": [
            {
                "field": "email",
                "error": "Invalid email format"
            }
        ]
    }
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No Content |
| `400` | Bad Request (validation error) |
| `401` | Unauthorized (invalid token) |
| `403` | Forbidden (no permission) |
| `404` | Not Found |
| `409` | Conflict (duplicate, etc.) |
| `429` | Rate Limited |
| `500` | Internal Server Error |

## Endpoint Reference

### Session Management

#### Create Session

```http
POST /sessions
Content-Type: application/json

{
    "assistant_id": "asst-123",
    "assistant_overrides": {
        "llm": {
            "temperature": 0.7
        }
    }
}

Response: 201 Created
{
    "session_id": "sess-unique-id",
    "tenant_id": "tenant-123",
    "created_at": "2024-12-11T10:30:00Z"
}
```

**Parameters**:
- `assistant_id` (optional): Pre-configured assistant to use
- `assistant_overrides` (optional): Runtime configuration overrides

**Returns**: Session ID for use in subsequent requests

#### List Sessions

```http
GET /sessions?skip=0&limit=20&state=completed

Response: 200 OK
{
    "sessions": [
        {
            "session_id": "sess-123",
            "assistant_id": "asst-456",
            "transport": "webrtc",
            "state": "completed",
            "created_at": "2024-12-11T10:30:00Z",
            "duration_seconds": 305.5
        }
    ],
    "total": 42
}
```

**Query Parameters**:
- `skip` (default: 0): Records to skip
- `limit` (default: 20): Records to return
- `state` (optional): Filter by state (preflight, in_flight, completed, etc.)
- `transport` (optional): Filter by transport (webrtc, twilio, plivo)
- `assistant_id` (optional): Filter by assistant

#### Get Session

```http
GET /sessions/{session_id}

Response: 200 OK
{
    "session_id": "sess-123",
    "assistant_id": "asst-456",
    "transport": "webrtc",
    "participants": [...],
    "state": "completed",
    "metadata": {},
    "created_at": "2024-12-11T10:30:00Z",
    "updated_at": "2024-12-11T10:35:00Z",
    "end_time": "2024-12-11T10:35:00Z"
}
```

#### End Session

```http
POST /sessions/{session_id}/end

Response: 200 OK
{
    "status": "completed",
    "summary": "Call completed successfully"
}
```

---

### WebRTC Communication

#### Offer Exchange

```http
POST /offer
Content-Type: application/json

{
    "session_id": "sess-123",
    "pc_id": "pc-unique-id",
    "sdp": "v=0\no=...",
    "type": "offer",
    "restart_pc": false
}

Response: 200 OK
{
    "pc_id": "pc-unique-id",
    "sdp": "v=0\no=...",
    "type": "answer",
    "session_id": "sess-123"
}
```

**Parameters**:
- `session_id` (required): Session to connect
- `pc_id` (required): WebRTC peer connection ID
- `sdp` (required): Session Description Protocol offer
- `type` (required): "offer" or "answer"
- `restart_pc` (optional): Restart ICE gathering

**Returns**: SDP answer for WebRTC connection

---

### Customer Profiles

#### Create Profile

```http
POST /customer-profiles
Content-Type: application/json

{
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe",
    "email": "john@example.com",
    "language_preference": "en",
    "preferences": {
        "communication_channel": "email"
    }
}

Response: 201 Created
{
    "profile_id": "prof-unique-id",
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe",
    "created_at": "2024-12-11T10:30:00Z"
}
```

**Parameters**:
- `primary_identifier` (required): Email or phone
- `identifier_type` (required): "email" or "phone"
- `name` (optional): Customer name
- `email` (optional): Email address
- `phone` (optional): Phone number (E.164 format)
- `language_preference` (optional): ISO 639-1 code
- `preferences` (optional): Custom preferences object

#### Get Profile

```http
GET /customer-profiles/{identifier}

Response: 200 OK
{
    "profile_id": "prof-unique-id",
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "ai_extracted_data": {
        "interests": ["email_marketing"],
        "follow_up_date": "2024-12-18"
    },
    "recent_call_summaries": [
        {
            "session_id": "sess-123",
            "summary_text": "Customer interested in enterprise plan",
            "outcome": "Interested",
            "timestamp": "2024-12-11T10:30:00Z",
            "transport_type": "webrtc"
        }
    ],
    "total_call_count": 4,
    "created_at": "2024-12-11T10:30:00Z",
    "updated_at": "2024-12-11T10:35:00Z"
}
```

**Parameters**:
- `{identifier}`: Email, phone, or profile ID

#### Update Profile

```http
PUT /customer-profiles/{profile_id}
Content-Type: application/json

{
    "name": "John Q. Doe",
    "language_preference": "es",
    "preferences": {
        "communication_channel": "sms"
    }
}

Response: 200 OK
{
    "profile_id": "prof-unique-id",
    "updated_at": "2024-12-11T10:40:00Z"
}
```

**Parameters**: Same as create (all optional)

#### Search Profiles

```http
GET /customer-profiles/search/query?q=john&limit=10

Response: 200 OK
{
    "results": [
        {
            "profile_id": "prof-123",
            "primary_identifier": "john@example.com",
            "name": "John Doe",
            "email": "john@example.com"
        },
        {
            "profile_id": "prof-456",
            "primary_identifier": "+1987654321",
            "name": "John Smith",
            "phone": "+1987654321"
        }
    ],
    "total": 2
}
```

**Query Parameters**:
- `q` (required): Search query
- `limit` (default: 10): Maximum results

#### Link Identity

```http
POST /customer-profiles/{profile_id}/identities
Content-Type: application/json

{
    "identity_type": "phone",
    "value": "+19876543210"
}

Response: 201 Created
{
    "profile_id": "prof-unique-id",
    "linked_identities": [
        {
            "identity_type": "phone",
            "value": "+19876543210",
            "linked_at": "2024-12-11T10:40:00Z"
        }
    ]
}
```

---

### Business Tools

#### Create Tool

```http
POST /business-tools
Content-Type: application/json

{
    "name": "send_email",
    "description": "Send an email to a customer",
    "parameters": [
        {
            "name": "recipient_email",
            "type": "email",
            "description": "Email recipient",
            "required": true,
            "examples": ["john@example.com"]
        }
    ],
    "api_config": {
        "base_url": "https://mail-api.example.com",
        "endpoint": "/send",
        "method": "POST",
        "authentication": {
            "type": "bearer",
            "token": "{{API_TOKEN}}"
        },
        "body_template": {
            "to": "{{recipient_email}}",
            "subject": "Hello"
        }
    },
    "engaging_words": "Sending your email now..."
}

Response: 201 Created
{
    "tool_id": "tool-unique-id",
    "name": "send_email",
    "created_at": "2024-12-11T10:30:00Z"
}
```

#### Get Tool

```http
GET /business-tools/{tool_id}

Response: 200 OK
{
    "tool_id": "tool-unique-id",
    "name": "send_email",
    "description": "Send an email to a customer",
    "parameters": [...],
    "api_config": {...},
    "engaging_words": "Sending your email now...",
    "created_at": "2024-12-11T10:30:00Z"
}
```

#### List Tools

```http
GET /business-tools?skip=0&limit=20

Response: 200 OK
{
    "tools": [
        {
            "tool_id": "tool-123",
            "name": "send_email",
            "description": "Send an email",
            "parameter_count": 3,
            "created_at": "2024-12-11T10:30:00Z"
        }
    ],
    "total": 5
}
```

#### Update Tool

```http
PUT /business-tools/{tool_id}
Content-Type: application/json

{
    "description": "Updated description",
    "engaging_words": "Processing your request..."
}

Response: 200 OK
{
    "success": true
}
```

#### Test Tool

```http
POST /business-tools/{tool_id}/test
Content-Type: application/json

{
    "parameters": {
        "recipient_email": "test@example.com",
        "subject": "Test Email"
    }
}

Response: 200 OK
{
    "success": true,
    "status_code": 200,
    "response_data": {
        "message_id": "msg-123"
    },
    "execution_time_ms": 145.3
}
```

**Returns**: Actual API call result for validation

#### Delete Tool

```http
DELETE /business-tools/{tool_id}

Response: 204 No Content
```

---

### Logs & Artifacts

#### List Session Logs

```http
GET /logs?skip=0&limit=20&session_id={session_id}

Response: 200 OK
{
    "logs": [
        {
            "log_id": "log-123",
            "session_id": "sess-456",
            "transport": "webrtc",
            "assistant_id": "asst-789",
            "session_state": "completed",
            "duration_seconds": 305.5,
            "created_at": "2024-12-11T10:30:00Z"
        }
    ],
    "total": 1
}
```

**Query Parameters**:
- `skip`, `limit`: Pagination
- `session_id` (optional): Filter by session
- `assistant_id` (optional): Filter by assistant
- `transport` (optional): Filter by transport

#### Get Session Artifacts

```http
GET /logs/{session_id}/artifacts

Response: 200 OK
{
    "artifacts": [
        {
            "artifact_type": "transcript",
            "content": {
                "messages": [...]
            }
        },
        {
            "artifact_type": "summary",
            "content": {
                "summary_text": "...",
                "outcome": "Interested"
            }
        },
        {
            "artifact_type": "metrics",
            "content": {
                "ttfb_ms": 450,
                "avg_latency_ms": 250
            }
        }
    ]
}
```

#### Export Logs

```http
GET /logs/{session_id}/export?format=json

Response: 200 OK
Content-Type: application/json
{
    "session_id": "sess-123",
    "exported_data": {...}
}
```

**Query Parameters**:
- `format`: "json" or "csv"

---

### Assistants

#### Create Assistant

```http
POST /assistants
Content-Type: application/json

{
    "name": "Customer Support Bot",
    "config": {
        "pipeline_mode": "traditional",
        "llm": {
            "provider": "openai",
            "model": "gpt-4o"
        },
        "stt": {
            "provider": "openai",
            "model": "whisper-1"
        },
        "tts": {
            "provider": "sarvam",
            "voice": "male_1"
        },
        "summarization_enabled": true
    }
}

Response: 201 Created
{
    "assistant_id": "asst-unique-id",
    "name": "Customer Support Bot",
    "created_at": "2024-12-11T10:30:00Z"
}
```

#### Get Assistant

```http
GET /assistants/{assistant_id}

Response: 200 OK
{
    "assistant_id": "asst-unique-id",
    "name": "Customer Support Bot",
    "config": {...},
    "created_at": "2024-12-11T10:30:00Z",
    "updated_at": "2024-12-11T10:30:00Z"
}
```

#### Update Assistant

```http
PUT /assistants/{assistant_id}
Content-Type: application/json

{
    "config": {
        "llm": {
            "temperature": 0.5
        }
    }
}

Response: 200 OK
{
    "success": true
}
```

#### List Assistants

```http
GET /assistants?skip=0&limit=20

Response: 200 OK
{
    "assistants": [...],
    "total": 5
}
```

---

### WebSocket Communication

#### Connect to WebSocket

```
WS wss://api.example.com/ws/{session_id}?token={bearer_token}
```

**Lifecycle**:

```
1. Client connects to WS endpoint with session_id
2. System upgrades connection to WebSocket
3. Audio frames flow in real-time
4. Connection closes when session ends
```

**Message Format**:

```json
{
    "type": "audio",
    "session_id": "sess-123",
    "audio_chunk": "base64-encoded-audio",
    "timestamp": "2024-12-11T10:30:00Z"
}
```

---

### Telephony Integration

#### Twilio Webhook

```http
POST /twilio/inbound
Content-Type: application/x-www-form-urlencoded

CallSid=CA123456789&From=+16175551212&To=+16175550123&...

Response: 200 OK
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://api.example.com/stream/CA123456789"/>
    </Connect>
</Response>
```

#### Plivo Webhook

```http
POST /plivo/inbound
Content-Type: application/json

{
    "event": "call_incoming",
    "call_uuid": "...",
    "from_number": "+1234567890",
    "to_number": "+0987654321"
}

Response: 200 OK
{
    "session_id": "sess-unique-id",
    "stream_url": "wss://api.example.com/stream/..."
}
```

---

## Authentication

### Bearer Token

All endpoints require an `Authorization` header with a Bearer token:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Validation

Tokens are validated on every request:

```
1. Extract token from Authorization header
2. Verify signature
3. Check expiration
4. Extract tenant_id from claims
5. Scope all operations to tenant
```

### Obtaining Tokens

```http
POST /auth/token
Content-Type: application/json

{
    "username": "user@example.com",
    "password": "secure-password"
}

Response: 200 OK
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

---

## Rate Limiting

The API implements rate limiting to prevent abuse:

**Limits**:
- 1000 requests per hour per token
- 100 concurrent requests per token

**Headers**:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1702383600
```

**Exceeded Limit Response**:
```json
{
    "status": "error",
    "error": {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Rate limit exceeded. Try again after 60 seconds.",
        "retry_after": 60
    }
}
```

---

## Pagination

Endpoints that return lists support pagination:

**Query Parameters**:
- `skip`: Number of records to skip (default: 0)
- `limit`: Number of records to return (default: 20, max: 100)

**Response Format**:
```json
{
    "items": [...],
    "total": 150,
    "skip": 0,
    "limit": 20
}
```

---

## Common Request Patterns

### Create with Nested Objects

```json
{
    "name": "Tool Name",
    "api_config": {
        "base_url": "https://api.example.com",
        "authentication": {
            "type": "bearer",
            "token": "..."
        }
    }
}
```

### Update Partial Fields

```json
{
    "name": "Updated Name"
}
```
Only provided fields are updated; others remain unchanged.

### Filter & Sort

```
GET /sessions?state=completed&sort_by=created_at&sort_order=-1
```

---

## Webhook Integration

Some endpoints support webhooks for event notifications:

```
POST {webhook_url}
Content-Type: application/json
X-Webhook-Signature: sha256=...

{
    "event_type": "session.completed",
    "event_id": "evt-123",
    "timestamp": "2024-12-11T10:35:00Z",
    "data": {
        "session_id": "sess-123",
        "state": "completed"
    }
}
```

---

## Quick Start Example

### 1. Create Assistant

```bash
curl -X POST https://api.example.com/api/v1/assistants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Bot",
    "config": {...}
  }'
# Response: {"assistant_id": "asst-123"}
```

### 2. Create Session

```bash
curl -X POST https://api.example.com/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "asst-123"
  }'
# Response: {"session_id": "sess-456"}
```

### 3. Connect WebRTC

```bash
# Client-side: Create WebRTC connection
# Exchange SDP with /offer endpoint
# Audio flows through session
```

### 4. End Session

```bash
curl -X POST https://api.example.com/api/v1/sessions/sess-456/end \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Retrieve Logs

```bash
curl -X GET https://api.example.com/api/v1/logs/sess-456/artifacts \
  -H "Authorization: Bearer $TOKEN"
```

---

## SDK Support

Official SDKs available for:
- **Python**: `pip install pipecat-sdk`
- **JavaScript/TypeScript**: `npm install @pipecat/sdk`
- **Go**: `go get github.com/pipecat/go-sdk`

---

## Support & Documentation

- **API Docs**: https://docs.example.com/api
- **Support**: support@example.com
- **Status Page**: https://status.example.com

---

## See Also

- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) - System design overview
- [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) - Business tools configuration
- [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Database schemas
- [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md) - Call summaries and AI extraction
- [README.md](README.md) - Documentation index

---

📖 **Return to**: [README.md](README.md)
