# Customer Profiles

> 👤 **Unified identity management** • Cross-channel customer context

## Overview

Customer Profiles provide a unified view of customers across all communication channels (WebRTC, phone, WhatsApp, etc.). They consolidate identity, preferences, history, and AI-extracted insights.

**Key Benefits**:
- Single identity across channels
- Persistent customer history
- AI-extracted insights
- Cross-channel context injection
- Automatic profile updates

---

## Quick Start

### Create a Profile

```bash
curl -X POST http://localhost:8000/api/v1/customer-profiles \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe"
  }'
```

### Link Additional Identities

```bash
# User calls from +1-234-567-8900
curl -X POST http://localhost:8000/api/v1/customer-profiles/{profile_id}/identities \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "identity_type": "phone",
    "value": "+12345678900"
  }'
```

### Use in Conversation

```python
# Automatically injected if use_in_prompt=True
AgentConfig(
    customer_profile_config={
        "use_in_prompt": True,
        "update_after_call": True
    }
)
```

---

## Profile Structure

### Core Fields

| Field | Type | Purpose |
|-------|------|---------|
| `profile_id` | string | Unique identifier |
| `primary_identifier` | string | Email or phone (canonical) |
| `identifier_type` | enum | "email" or "phone" |
| `name` | string | Customer's name |
| `email` | string | Email address |
| `phone` | string | Phone (E.164 format) |

### Preferences

| Field | Type | Purpose |
|-------|------|---------|
| `language_preference` | string | ISO 639-1 code (e.g., "en", "es") |
| `preferences` | object | Custom user-set preferences |

### AI-Extracted Data

```json
{
    "ai_extracted_data": {
        "interests": ["email_marketing", "crm"],
        "company": "Tech Inc",
        "communication_preferences": "email",
        "follow_up_date": "2024-12-18",
        "budget_range": "$50k-$100k",
        "product_affinity": "enterprise"
    }
}
```

### Call History

```json
{
    "recent_call_summaries": [
        {
            "session_id": "sess-123",
            "summary_text": "Discussed enterprise plan pricing",
            "outcome": "Interested",
            "timestamp": "2024-12-11T10:30:00Z",
            "transport_type": "webrtc",
            "duration_seconds": 305
        }
    ],
    "aggregated_older_summary": "Customer has had 4 previous calls exploring our product...",
    "total_call_count": 5,
    "last_interaction_at": "2024-12-11T10:30:00Z"
}
```

---

## Identity Linking

### How It Works

1. **Primary Identifier**: Email or phone used to create profile
2. **Linked Identities**: Additional email/phone addresses
3. **Unified Lookup**: Any identifier resolves to same profile

### Use Cases

**Example 1: Email + Phone**
```
Profile created with: john@example.com
Later linked: +1-234-567-8900
Now searchable by both identifiers
```

**Example 2: Work + Personal**
```
Profile created with: john.doe@company.com
Later linked: john.personal@gmail.com
Both resolve to same customer
```

### Linking Process

```python
# 1. Create profile (email)
POST /customer-profiles
{
    "primary_identifier": "john@company.com",
    "identifier_type": "email"
}

# 2. Later, link phone
POST /customer-profiles/{profile_id}/identities
{
    "identity_type": "phone",
    "value": "+12025551234"
}

# 3. Lookup by either identifier
GET /customer-profiles/john@company.com  # ✅ Found
GET /customer-profiles/+12025551234      # ✅ Found (same profile)
```

---

## Call History & Summaries

### Rolling Window Strategy

Profiles maintain:
- **4 Most Recent** call summaries (full details)
- **1 Aggregated Summary** of calls 5+ (space efficient)

### Automatic Updates

When `update_after_call=True`:

```
Session End
    ↓
Generate Summary
    ↓
Extract AI Insights
    ↓
Load Current Profile
    ↓
Add Summary to recent_call_summaries
    ↓
If > 4 summaries:
  Aggregate older ones
    ↓
Save Profile
```

### Example Profile State

```json
{
    "profile_id": "prof-123",
    "primary_identifier": "jane@company.com",
    "name": "Jane Smith",
    
    "recent_call_summaries": [
        {
            "session_id": "sess-10",
            "summary_text": "Discussed custom implementation",
            "outcome": "Interested",
            "timestamp": "2024-12-11T15:30:00Z"
        },
        {
            "session_id": "sess-9",
            "summary_text": "Technical Q&A about integrations",
            "outcome": "Interested",
            "timestamp": "2024-12-10T14:00:00Z"
        }
        // ... 2 more recent summaries
    ],
    
    "aggregated_older_summary": "Jane has had 6 previous interactions. Initially skeptical but impressed by security features. Has integrated 2 test environments. High likelihood of enterprise purchase.",
    
    "total_call_count": 10,
    "last_interaction_at": "2024-12-11T15:30:00Z"
}
```

---

## Using Profiles in Conversations

### Option 1: Inject into Prompt

When `use_in_prompt=True`:

```
System Prompt:
"You are a customer service agent. 
The customer is Jane Smith from Acme Inc. 
They are interested in email_marketing and crm products.
Previous interactions show they prefer technical details.
Budget range: $50k-$100k"

[Conversation proceeds with this context]
```

### Option 2: No Injection

When `use_in_prompt=False`:

```
System Prompt:
"You are a customer service agent."

[Conversation is generic, but profile is still updated after]
```

### Switching Between Options

```python
# Start without profile injection (better for testing)
config = AgentConfig(
    customer_profile_config={
        "use_in_prompt": False,
        "update_after_call": True
    }
)

# After validating extraction quality, enable injection
config = AgentConfig(
    customer_profile_config={
        "use_in_prompt": True,  # ← Enable this
        "update_after_call": True
    }
)
```

---

## API Reference

### Create Profile

```http
POST /customer-profiles
Content-Type: application/json

{
    "primary_identifier": "john@example.com",
    "identifier_type": "email",
    "name": "John Doe",
    "language_preference": "en"
}

Response: 201 Created
{
    "profile_id": "prof-123",
    "primary_identifier": "john@example.com",
    ...
}
```

### Get Profile

```http
GET /customer-profiles/john@example.com
# or
GET /customer-profiles/prof-123
# or
GET /customer-profiles/+12345678900

Response: 200 OK
{
    "profile_id": "prof-123",
    "name": "John Doe",
    ...
}
```

### Update Profile

```http
PUT /customer-profiles/prof-123
Content-Type: application/json

{
    "name": "John Q. Doe",
    "language_preference": "es"
}

Response: 200 OK
```

### Search Profiles

```http
GET /customer-profiles/search/query?q=john&limit=10

Response: 200 OK
{
    "results": [
        {
            "profile_id": "prof-123",
            "primary_identifier": "john@example.com",
            "name": "John Doe"
        }
    ],
    "total": 1
}
```

### Link Identity

```http
POST /customer-profiles/prof-123/identities
Content-Type: application/json

{
    "identity_type": "phone",
    "value": "+12345678900"
}

Response: 201 Created
```

### Delete Profile

```http
DELETE /customer-profiles/prof-123

Response: 204 No Content
```

See [API_GUIDE.md](API_GUIDE.md#customer-profiles) for complete reference.

---

## Configuration Options

### Agent Configuration

```python
CustomerProfileConfig(
    use_in_prompt=False,           # Inject profile into system prompt
    update_after_call=False,       # Update profile after each call
    ai_required_fields=[           # What to extract from conversation
        "name",
        "interests",
        "communication_preferences",
        "follow_up_date",
        "budget_range"
    ]
)
```

### Default Extraction Fields

From `src/app/core/constants.py`:

```python
CUSTOMER_PROFILE_AI_REQUIRED_FIELDS = [
    "name",
    "phone",
    "email",
    "interests",
    "communication_preferences",
    "follow_up_date",
    "notes",
    "budget_range"
]
```

---

## Integration Scenarios

### Scenario 1: Support Center

```python
# Track support interactions without injecting profile
config = AgentConfig(
    customer_profile_config={
        "use_in_prompt": False,
        "update_after_call": True,
        "ai_required_fields": [
            "last_issue_resolved",
            "product_version",
            "satisfaction",
            "next_steps"
        ]
    }
)

# After each support call:
# - Profile updated with issue resolution
# - History available for next agent
# - Satisfaction tracked
```

### Scenario 2: Sales Pipeline

```python
# Inject profile for personalized pitches
config = AgentConfig(
    customer_profile_config={
        "use_in_prompt": True,
        "update_after_call": True,
        "ai_required_fields": [
            "interests",
            "budget_range",
            "decision_timeline",
            "stakeholders",
            "current_solution"
        ]
    }
)

# During sales call:
# - AI sees customer history (previous calls, interests)
# - Tailors pitch accordingly
# - Extracts new insights
```

### Scenario 3: Outbound Campaign

```python
# Different profile config per stage
if stage == "qualification":
    use_in_prompt = False
elif stage == "demo":
    use_in_prompt = True
elif stage == "closing":
    use_in_prompt = True
```

---

## Best Practices

### 1. Start Simple

```python
# Phase 1: Track only
config = AgentConfig(
    customer_profile_config={
        "use_in_prompt": False,
        "update_after_call": True
    }
)
```

### 2. Validate Extraction

Before enabling injection:
- Review extracted data quality
- Adjust `ai_required_fields` as needed
- Test with small user group

### 3. Customize Fields

```python
# Only extract what you need
ai_required_fields=[
    "interests",
    "follow_up_date",
    "budget_range"
]

# Don't extract unused fields
```

### 4. Monitor Quality

```python
# Regularly check extraction
profiles = db.customer_profiles.find(
    {"ai_extracted_data": {"$exists": True}}
)
for profile in profiles:
    review_extraction_quality(profile)
```

### 5. Privacy & Compliance

- Only store necessary data
- Delete old data per retention policy
- Log all profile access
- Encrypt sensitive fields

---

## Troubleshooting

**Issue**: Profile not found
- **Solution**: Check identifier format (email vs phone)
- **Solution**: Try search endpoint instead

**Issue**: Extraction quality poor
- **Solution**: Customize `ai_required_fields`
- **Solution**: Improve system prompt
- **Solution**: Use better LLM model

**Issue**: Profile not updating
- **Solution**: Check `update_after_call=True`
- **Solution**: Verify call completed (not interrupted)
- **Solution**: Check logs for errors

**Issue**: Identity linking conflicts
- **Solution**: Check linked identity doesn't already belong to another profile
- **Solution**: Unlink first if needed

---

## See Also

- [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md) - How profiles are updated
- [API_GUIDE.md](API_GUIDE.md) - Profile API endpoints
- [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Profile schema
- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) - System data flow
- [README.md](README.md) - Documentation index

---

📖 **Return to**: [README.md](README.md)

