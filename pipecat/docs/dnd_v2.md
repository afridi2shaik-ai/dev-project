# Telephony DND v2

This document describes the structured Do Not Disturb (DND) v2 implementation for telephony-only enforcement.

## Overview

DND v2 provides assistant-configurable, telephony-only blocking of outbound and inbound calls based on customer profile settings. Unlike legacy boolean DND, this implementation uses a structured object with audit trails and granular control.

## Schema

### CustomerProfile.dnd

The DND configuration is stored as a structured object in the `CustomerProfile.dnd` field:

```json
{
  "dnd": {
    "channels": {
      "telephony": {
        "outbound": false,
        "inbound": false
      }
    },
    "audit": {
      "updated_at": "2025-12-17T10:30:00Z",
      "updated_by": null,
      "reason": null,
      "source_session_id": null,
      "source_timestamp": null
    }
  }
}
```

### Fields

- `channels.telephony.outbound`: Boolean flag to block outbound telephony calls
- `channels.telephony.inbound`: Boolean flag to block inbound telephony calls
- `audit.updated_at`: Timestamp of last DND change
- `audit.updated_by`: Who made the change (e.g., "ai_extraction", "api_user")
- `audit.reason`: Reason for the change (e.g., "customer_opt_out_detected")
- `audit.source_session_id`: Session ID that triggered the change
- `audit.source_timestamp`: Timestamp when the triggering event occurred

## Enforcement

### Telephony-Only

DND enforcement applies **only** to telephony transports (`twilio`, `plivo`). WebRTC/WebSocket sessions are never blocked by DND settings.

### Assistant Configuration

DND enforcement is controlled by assistant configuration under `customer_profile_config`:

```json
{
  "customer_profile_config": {
    "enforce_dnd": true,
    "dnd_policy": "block_outbound_only"
  }
}
```

### Policies

- `"block_outbound_only"` (default): Block outbound calls when `telephony.outbound=true`
- `"block_inbound_only"`: Block inbound calls when `telephony.inbound=true`
- `"block_all"`: Block calls if either `telephony.outbound=true` or `telephony.inbound=true`
- `"ignore"`: Never block calls due to DND

### Master Toggle

The `enforce_dnd` field provides a master toggle:
- `true` (default): Enable DND enforcement according to the policy
- `false`: Disable DND enforcement entirely

### Direction Detection

Call direction is determined in this priority order:

1. `metadata.call_direction` (normalized: `outbound-api` → `outbound`)
2. Participant ordering inference:
   - SYSTEM participant first → outbound call
   - USER participant first → inbound call

### Blocking Behavior

When a telephony session creation is blocked due to DND:

- **Twilio**: Returns XML `<Response><Hangup/></Response>`
- **Plivo**: Returns XML `<Response><Hangup/></Response>`
- **Error**: Raises `DndBlockedError` with direction, policy, and profile details

## Post-Call Auto-Set

After each call, AI extraction analyzes the conversation transcript to detect opt-out requests:

- **Detection**: Looks for phrases like "don't call me", "stop calling", "do not disturb"
- **Flags Set**: Sets `telephony.outbound=true` when outbound opt-out detected
- **Never Unset**: DND flags are only set, never automatically cleared
- **Audit**: Stamps audit fields with session ID and timestamp

## Database Backfill

### Self-Heal on Read

When reading customer profiles:

- Missing/null `dnd` field is auto-normalized to default object
- Changes are **persisted** to the database immediately
- Legacy boolean `dnd` values are **rejected** with clear errors

### Default Object

```json
{
  "channels": {
    "telephony": {
      "outbound": false,
      "inbound": false
    }
  },
  "audit": {
    "updated_at": "<current_timestamp>",
    "updated_by": null,
    "reason": null,
    "source_session_id": null,
    "source_timestamp": null
  }
}
```

## API Integration

### Customer Profile APIs

DND settings can be managed via standard customer profile CRUD operations:

- **Create**: Include `dnd` object in `CustomerProfileCreateRequest`
- **Update**: Include `dnd` object in `CustomerProfileUpdateRequest`
- **Read**: `CustomerProfileResponse` includes current `dnd` settings

### Session Creation

DND enforcement happens automatically during telephony session creation:

1. Assistant config is resolved (with fallback defaults if fetch fails)
2. Customer profile is looked up by phone identifier
3. DND settings are checked against policy and direction
4. Session is blocked or allowed accordingly

## Migration Notes

### Legacy Boolean DND

Profiles with legacy `dnd: true/false` will be rejected on read with an error message. These must be manually migrated or the profiles recreated with the structured format.

### Backfill Process

Existing profiles without DND settings will be automatically backfilled to default objects on first read. This ensures all profiles have consistent DND structure.
