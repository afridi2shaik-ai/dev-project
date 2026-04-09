# Customer Profile Manager Guide

## Overview
Unified customer profiles consolidate identities (email/phone), preferences, AI-extracted insights, and rolling call history. Profiles are stored per-tenant in `customer_profiles` and resolved at session start for personalization and language preference overrides.

## Schemas
- `CustomerProfile` (`src/app/schemas/core/customer_profile.py`): primary_identifier + identifier_type, name/email/phone, language_preference, preferences, ai_extracted_data, linked_identities, rolling `recent_call_summaries` (max 4), `aggregated_older_summary`, counters/timestamps.
- Requests: `CustomerProfileCreateRequest`, `CustomerProfileUpdateRequest`, `LinkIdentityRequest`.
- Responses/params: `CustomerProfileResponse`, path/query param models for identifier/profile_id/link/list/search.

## Constants
Defined in `src/app/core/constants.py`:
- Aggregation: model `gpt-4o-mini`, temp `0.3`, max tokens `600`, max words `500`.
- Extraction: model `gpt-4o-mini`, temp `0.3`, max tokens `500`.
- Rolling window: `CUSTOMER_PROFILE_MAX_RECENT_SUMMARIES = 4`.
- Required AI fields: `["language_preference", "name, "email"]`.

## Manager (`src/app/managers/customer_profile_manager.py`)
- CRUD with conflict checks on identifiers.
- Identity link/unlink with safeguards against cross-profile reuse; auto-fills email/phone when missing.
- Call recording: maintains last 4 summaries; aggregates older via LLM; updates totals/last interaction.
- AI extraction: formats full session artifacts (transcript, summary, metrics, tool usage, participants, hangup, context) and uses LLM to enrich `ai_extracted_data`, ensuring required fields + `extracted_at`.
- List/search with pagination and regex-based matching on name/email/phone/primary_identifier.

## Service (`src/app/services/customer_profile_service.py`)
- Resolves profile per session (telephony → phone first; WebRTC/WebSocket → email first; fall back to linked identities).
- Builds full and brief context strings (preferences, AI insights, call history) and surfaces language preference.
- Exposed via `enrich_session_context` and helper `get_customer_profile_context`.

## API (`src/app/api/customer_profile_api.py`)
Base path: `/vagent/api/customer-profiles`
- `GET /{identifier}`: fetch by profile_id/email/phone.
- `POST /`: create.
- `PATCH /{profile_id}`: update.
- `DELETE /{profile_id}`: delete.
- `POST /{profile_id}/link`: link identity.
- `DELETE /{profile_id}/link/{identity_type}/{value}`: unlink.
- `GET /`: list with pagination/sort.
- `GET /search/query`: search by name/email/phone.
All inputs are schema-driven (path/query models + body schemas).

## Session Lifecycle Integration (`src/app/core/transports/base_transport_service.py`)
- At session start: resolves profile context (phone/email aware), stores context/brief context/profile_id in session metadata, and surfaces language preference override.
- Post-call: records call summary to profile (auto-creates on first contact), maintains rolling summaries, and triggers AI extraction of insights; runs asynchronously to avoid blocking cleanup.

## Call History & AI Extraction Flow
1. Pipeline completes → summary generated → artifacts saved.
2. Manager `record_call_completion` updates recent_call_summaries, aggregates overflow, increments totals.
3. `extract_and_update_ai_data` ingests transcript/summary/tool usage/metrics/session context to enrich `ai_extracted_data` with required fields + timestamp.

## Notes
- OpenAI API key required for aggregation/extraction.
- Language preference is taken from user-set field when present, otherwise AI-detected value.
- Rolling history keeps last 4 summaries; older content is condensed to keep prompts lean.


