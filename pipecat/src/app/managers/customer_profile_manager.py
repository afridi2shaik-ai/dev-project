"""
Customer Profile Manager for unified user identity management.

Handles CRUD, identity linking safeguards, call history management with rolling
aggregation, and AI extraction of customer insights.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.constants import (
    CUSTOMER_PROFILE_AGGREGATION_LLM_MODEL,
    CUSTOMER_PROFILE_AGGREGATION_LLM_TEMPERATURE,
    CUSTOMER_PROFILE_AGGREGATION_MAX_SUMMARY_WORDS,
    CUSTOMER_PROFILE_AGGREGATION_MAX_TOKENS,
    CUSTOMER_PROFILE_AI_REQUIRED_FIELDS,
    CUSTOMER_PROFILE_EXTRACTION_LLM_MODEL,
    CUSTOMER_PROFILE_EXTRACTION_LLM_TEMPERATURE,
    CUSTOMER_PROFILE_EXTRACTION_MAX_TOKENS,
    CUSTOMER_PROFILE_MAX_RECENT_SUMMARIES,
)
from app.schemas.core.customer_profile import (
    CallSummary,
    CustomerProfile,
    CustomerProfileCreateRequest,
    CustomerProfileUpdateRequest,
    LinkedIdentity,
)


class CustomerProfileManager:
    """
    Manages customer profiles with unified identity across channels.

    Responsibilities:
    - Profile CRUD operations
    - Identity linking (email <-> phone) with conflict safeguards
    - Call history with rolling summary aggregation
    - AI extraction of customer insights
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["customer_profiles"]

    def _ensure_dnd_v2(self, data: dict) -> tuple[dict, bool]:
        """Ensure profile has DND v2 structure. Returns (updated_data, was_changed)."""
        if isinstance(data.get("dnd"), bool):
            raise ValueError("Legacy dnd: bool is not supported")

        if "dnd" not in data or data["dnd"] is None:
            # Create default DND object
            from app.schemas.core.customer_profile import CustomerDnd
            default_dnd = CustomerDnd()
            data["dnd"] = default_dnd.model_dump()
            return data, True

        return data, False

    # -------------------------------------------------------------------------
    # Profile CRUD Operations
    # -------------------------------------------------------------------------

    async def get_by_profile_id(self, profile_id: str) -> CustomerProfile | None:
        """Get a customer profile by its unique profile ID."""
        data = await self.collection.find_one({"_id": profile_id})
        if data:
            # Apply DND v2 backfill if needed
            updated_data, was_changed = self._ensure_dnd_v2(data)
            if was_changed:
                await self.collection.update_one(
                    {"_id": profile_id},
                    {"$set": {"dnd": updated_data["dnd"], "updated_at": datetime.datetime.now(datetime.UTC)}}
                )
                logger.debug(f"Backfilled DND v2 structure for profile {profile_id}")
            return CustomerProfile(**updated_data)
        return None

    async def get_by_identifier(self, identifier: str) -> CustomerProfile | None:
        """
        Find a customer profile by any identifier (email, phone, or linked identity).

        Search order:
        1. Primary identifier (email or phone fields directly)
        2. Linked identities
        """
        identifier = identifier.strip()
        if not identifier:
            return None

        # Normalize phone identifiers (e.g., "+9199..." vs "9199...") to avoid
        # duplicate profiles and make lookups resilient to provider formatting.
        from app.utils.validation.field_validators import normalize_phone_identifier

        candidates: list[str] = [identifier]
        normalized = normalize_phone_identifier(identifier)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

        # Also search common variants (+/no-+), because historical data may have
        # been stored inconsistently.
        for val in list(candidates):
            if val.startswith("+"):
                no_plus = val[1:]
                if no_plus and no_plus not in candidates:
                    candidates.append(no_plus)
            else:
                plus = f"+{val}"
                if plus not in candidates:
                    candidates.append(plus)

        query = {
            "$or": [
                {"email": {"$in": candidates}},
                {"phone": {"$in": candidates}},
                {"primary_identifier": {"$in": candidates}},
                {"linked_identities.value": {"$in": candidates}},
            ]
        }

        # Use a deterministic selection strategy in case multiple profiles match
        # the same identifier (common when historical data contains +/no-+ duplicates).
        matches = await self.collection.find(query).to_list(length=10)
        if matches:
            if len(matches) > 1:
                logger.warning(
                    f"⚠️ Multiple customer profiles match identifier '{identifier}'. "
                    f"Choosing canonical profile deterministically. "
                    f"matched_ids={[m.get('_id') for m in matches]}"
                )

            preferred_phone = normalized

            def _score(doc: dict) -> tuple[int, int, int]:
                """
                Higher is better.
                Priority:
                1) primary_identifier matches normalized E.164 (canonical)
                2) phone field matches normalized E.164
                3) total_call_count (keep the richer profile)
                """
                score = 0
                if preferred_phone:
                    if doc.get("primary_identifier") == preferred_phone:
                        score += 100
                    if doc.get("phone") == preferred_phone:
                        score += 25
                total_calls = doc.get("total_call_count") or 0
                return (score, int(total_calls), 1)

            matches.sort(key=_score, reverse=True)
            data = matches[0]

            # Apply DND v2 backfill if needed
            updated_data, was_changed = self._ensure_dnd_v2(data)
            if was_changed:
                await self.collection.update_one(
                    {"_id": data["_id"]},
                    {"$set": {"dnd": updated_data["dnd"], "updated_at": datetime.datetime.now(datetime.UTC)}}
                )
                logger.debug(f"Backfilled DND v2 structure for profile {data['_id']}")
            return CustomerProfile(**updated_data)
        return None

    async def create_profile(self, request: CustomerProfileCreateRequest) -> CustomerProfile:
        """
        Create a new customer profile.

        Raises:
            ValueError: If a profile with the same identifier already exists.
        """
        # Normalize phone primary identifiers to E.164 to prevent duplicates
        # (e.g., "+9199..." vs "9199...") at creation time.
        from app.utils.validation.field_validators import normalize_phone_identifier

        primary_identifier = request.primary_identifier
        if request.identifier_type == "phone":
            normalized_primary = normalize_phone_identifier(primary_identifier)
            if normalized_primary:
                primary_identifier = normalized_primary

        existing = await self.get_by_identifier(primary_identifier)
        if existing:
            raise ValueError(f"A profile already exists for identifier: {primary_identifier}")

        now = datetime.datetime.now(datetime.UTC)

        email_value = request.email or (primary_identifier if request.identifier_type == "email" else None)

        phone_source = request.phone or (primary_identifier if request.identifier_type == "phone" else None)
        phone_value = normalize_phone_identifier(phone_source) if phone_source else None

        profile = CustomerProfile(
            primary_identifier=primary_identifier,
            identifier_type=request.identifier_type,
            name=request.name,
            email=email_value,
            phone=phone_value,
            language_preference=request.language_preference,
            preferences=request.preferences,
            created_at=now,
            updated_at=now,
        )

        await self.collection.insert_one(profile.model_dump(by_alias=True))
        logger.info(f"Created customer profile: {profile.profile_id} for {primary_identifier}")
        return profile

    async def update_profile(
        self,
        profile_id: str,
        request: CustomerProfileUpdateRequest,
    ) -> CustomerProfile | None:
        """Update an existing customer profile."""
        update_fields: dict[str, Any] = {"updated_at": datetime.datetime.now(datetime.UTC)}

        if request.name is not None:
            update_fields["name"] = request.name
        if request.email is not None:
            update_fields["email"] = request.email
        if request.phone is not None:
            update_fields["phone"] = request.phone
        if request.language_preference is not None:
            update_fields["language_preference"] = request.language_preference
        if request.preferences is not None:
            existing = await self.get_by_profile_id(profile_id)
            if existing:
                merged_prefs = {**existing.preferences, **request.preferences}
                update_fields["preferences"] = merged_prefs

        result = await self.collection.update_one({"_id": profile_id}, {"$set": update_fields})
        if result.matched_count == 0:
            return None

        return await self.get_by_profile_id(profile_id)

    # -------------------------------------------------------------------------
    # DND (Do Not Disturb)
    # -------------------------------------------------------------------------

    async def clear_telephony_outbound_dnd(
        self,
        profile_id: str,
        *,
        session_id: str | None = None,
        updated_by: str = "system_auto_clear",
        reason: str = "inbound_call_received",
    ) -> CustomerProfile | None:
        """Clear outbound telephony DND for a profile and persist audit info.

        This is intentionally an explicit, deterministic update (not AI-driven).
        """
        profile = await self.get_by_profile_id(profile_id)
        if not profile:
            return None

        now = datetime.datetime.now(datetime.UTC)

        # Ensure profile has DND object
        if not profile.dnd:
            from app.schemas.core.customer_profile import CustomerDnd

            profile.dnd = CustomerDnd()

        # If already cleared, avoid unnecessary writes but keep updated_at current? (No)
        if not profile.dnd.channels.telephony.outbound:
            return profile

        profile.dnd.channels.telephony.outbound = False
        profile.dnd.audit.updated_at = now
        profile.dnd.audit.updated_by = updated_by
        profile.dnd.audit.reason = reason
        profile.dnd.audit.source_session_id = session_id
        profile.dnd.audit.source_timestamp = now

        await self.collection.update_one(
            {"_id": profile_id},
            {"$set": {"dnd": profile.dnd.model_dump(), "updated_at": now}},
        )

        return await self.get_by_profile_id(profile_id)

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a customer profile by ID."""
        result = await self.collection.delete_one({"_id": profile_id})
        return result.deleted_count > 0

    # -------------------------------------------------------------------------
    # Identity Linking
    # -------------------------------------------------------------------------

    async def link_identity(
        self,
        profile_id: str,
        identity_type: str,
        value: str,
    ) -> CustomerProfile | None:
        """
        Link an additional identity to a customer profile.

        Safeguards against linking the same identity across profiles.
        """
        value = value.strip()

        existing = await self.get_by_identifier(value)
        if existing and existing.profile_id != profile_id:
            raise ValueError(f"Identity {value} is already linked to profile {existing.profile_id}")

        profile = await self.get_by_profile_id(profile_id)
        if not profile:
            return None

        for linked in profile.linked_identities:
            if linked.value == value:
                logger.debug(f"Identity {value} already linked to profile {profile_id}")
                return profile

        new_identity = LinkedIdentity(identity_type=identity_type, value=value)

        now = datetime.datetime.now(datetime.UTC)
        update_doc: dict[str, Any] = {
            "$push": {"linked_identities": new_identity.model_dump()},
            "$set": {"updated_at": now},
        }

        if identity_type == "email" and not profile.email:
            update_doc["$set"]["email"] = value
        elif identity_type == "phone" and not profile.phone:
            update_doc["$set"]["phone"] = value

        await self.collection.update_one({"_id": profile_id}, update_doc)
        logger.info(f"Linked {identity_type}={value} to profile {profile_id}")
        return await self.get_by_profile_id(profile_id)

    async def unlink_identity(
        self,
        profile_id: str,
        identity_type: str,
        value: str,
    ) -> CustomerProfile | None:
        """Remove a linked identity from a customer profile."""
        result = await self.collection.update_one(
            {"_id": profile_id},
            {
                "$pull": {"linked_identities": {"identity_type": identity_type, "value": value}},
                "$set": {"updated_at": datetime.datetime.now(datetime.UTC)},
            },
        )

        if result.matched_count == 0:
            return None

        logger.info(f"Unlinked {identity_type}={value} from profile {profile_id}")
        return await self.get_by_profile_id(profile_id)

    # -------------------------------------------------------------------------
    # Call History Management
    # -------------------------------------------------------------------------

    async def record_call_completion(
        self,
        identifier: str,
        identifier_type: str,
        call_summary: CallSummary,
        customer_name: str | None = None,
    ) -> CustomerProfile:
        """
        Record a completed call and update the customer's call history.

        - Finds or creates a profile for the identifier
        - Maintains rolling recent summaries (max configured)
        - Aggregates older summaries via LLM
        """
        profile = await self.get_by_identifier(identifier)

        if not profile:
            create_request = CustomerProfileCreateRequest(
                primary_identifier=identifier,
                identifier_type=identifier_type,  # type: ignore[arg-type]
                name=customer_name,
            )
            profile = await self.create_profile(create_request)
            logger.info(f"Auto-created profile {profile.profile_id} for {identifier}")

        current_summaries = list(profile.recent_call_summaries)
        aggregated_summary = profile.aggregated_older_summary

        current_summaries.insert(0, call_summary)

        if len(current_summaries) > CUSTOMER_PROFILE_MAX_RECENT_SUMMARIES:
            oldest_summary = current_summaries.pop()
            aggregated_summary = await self._aggregate_summary(aggregated_summary, oldest_summary)

        now = datetime.datetime.now(datetime.UTC)

        await self.collection.update_one(
            {"_id": profile.profile_id},
            {
                "$set": {
                    "recent_call_summaries": [s.model_dump() for s in current_summaries],
                    "aggregated_older_summary": aggregated_summary,
                    "total_call_count": profile.total_call_count + 1,
                    "last_interaction_at": now,
                    "updated_at": now,
                    **({"name": customer_name} if customer_name and not profile.name else {}),
                },
            },
        )

        logger.info(
            f"Recorded call for profile {profile.profile_id}: "
            f"total_calls={profile.total_call_count + 1}, "
            f"recent_summaries={len(current_summaries)}"
        )

        return await self.get_by_profile_id(profile.profile_id)  # type: ignore[return-value]

    async def _aggregate_summary(
        self,
        existing_aggregate: str | None,
        old_summary: CallSummary,
    ) -> str:
        """Use LLM to merge an old summary into the existing aggregate."""
        try:
            from openai import AsyncOpenAI

            from app.core.config import settings

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            prompt = f"""You are summarizing a customer's call history for a voice AI system.

Previous aggregate summary of older calls:
{existing_aggregate or "No previous interactions recorded."}

New call to incorporate into the aggregate:
- Date: {old_summary.timestamp.strftime("%Y-%m-%d %H:%M")}
- Transport: {old_summary.transport_type}
- Outcome: {old_summary.outcome or "Unknown"}
- Summary: {old_summary.summary_text}

Create a concise updated aggregate summary that:
1. Preserves key facts about the customer (preferences, issues, requests)
2. Notes patterns in their interactions
3. Keeps important context for future personalization
4. Stays under {CUSTOMER_PROFILE_AGGREGATION_MAX_SUMMARY_WORDS} words

Output only the updated aggregate summary, no preamble."""

            response = await client.chat.completions.create(
                model=CUSTOMER_PROFILE_AGGREGATION_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=CUSTOMER_PROFILE_AGGREGATION_LLM_TEMPERATURE,
                max_tokens=CUSTOMER_PROFILE_AGGREGATION_MAX_TOKENS,
            )

            aggregated = response.choices[0].message.content
            logger.debug(f"Generated aggregate summary: {len(aggregated or '')} chars")
            return aggregated or existing_aggregate or ""

        except Exception as e:
            logger.error(f"Failed to aggregate summary via LLM: {e}")
            if existing_aggregate:
                return f"{existing_aggregate}\n\n[{old_summary.timestamp.strftime('%Y-%m-%d')}] {old_summary.summary_text}"
            return f"[{old_summary.timestamp.strftime('%Y-%m-%d')}] {old_summary.summary_text}"

    # -------------------------------------------------------------------------
    # AI Data Extraction
    # -------------------------------------------------------------------------

    def _format_session_data_for_extraction(self, session_data: dict[str, Any]) -> str:
        """Format all session artifacts for LLM analysis."""
        sections = []

        if "transcript" in session_data:
            sections.append("=== CONVERSATION TRANSCRIPT ===")
            for msg in session_data["transcript"].get("messages", []):
                role = msg.get("role", "unknown").upper()
                text = msg.get("text", "")
                msg_type = msg.get("type", "")

                if msg_type == "tool_call":
                    tool_name = msg.get("tool_details", {}).get("name", "unknown")
                    tool_args = msg.get("tool_details", {}).get("arguments", {})
                    sections.append(f"[TOOL CALL: {tool_name}] Args: {json.dumps(tool_args, ensure_ascii=False)}")
                elif msg_type == "tool_result":
                    tool_name = msg.get("tool_details", {}).get("name", "unknown")
                    sections.append(f"[TOOL RESULT: {tool_name}]")
                else:
                    sections.append(f"{role}: {text}")

        if "summary" in session_data:
            sections.append("\n=== CALL SUMMARY ===")
            summary = session_data["summary"]
            if isinstance(summary, dict):
                if summary.get("text"):
                    sections.append(f"Summary: {summary['text']}")
                if summary.get("outcome"):
                    sections.append(f"Outcome: {summary['outcome']}")
            else:
                sections.append(str(summary))

        if "transport_details" in session_data:
            sections.append("\n=== CALL DETAILS ===")
            sections.append(json.dumps(session_data["transport_details"], indent=2, ensure_ascii=False))

        if "participant_data" in session_data:
            sections.append("\n=== PARTICIPANT DATA ===")
            sections.append(json.dumps(session_data["participant_data"], indent=2, ensure_ascii=False))

        if "session_context" in session_data:
            sections.append("\n=== SESSION CONTEXT ===")
            sections.append(json.dumps(session_data["session_context"], indent=2, ensure_ascii=False))

        if "tool_usage" in session_data and session_data["tool_usage"]:
            sections.append("\n=== TOOLS USED ===")
            sections.append(json.dumps(session_data["tool_usage"], indent=2, ensure_ascii=False))

        if "hangup" in session_data:
            sections.append("\n=== CALL END INFO ===")
            sections.append(json.dumps(session_data["hangup"], indent=2, ensure_ascii=False))

        if "metrics" in session_data:
            sections.append("\n=== CALL METRICS ===")
            metrics = session_data["metrics"]
            key_metrics = {
                "duration": metrics.get("duration"),
                "turn_count": metrics.get("turn_analytics", {}).get("total_turns")
                if metrics.get("turn_analytics")
                else None,
            }
            sections.append(json.dumps(key_metrics, indent=2, ensure_ascii=False))

        return "\n".join(sections)

    async def extract_and_update_ai_data(
        self,
        profile_id: str,
        session_data: dict[str, Any],
        call_outcome: str | None = None,
        ai_required_fields: list[str] | None = None,
        session_id: str | None = None,
    ) -> CustomerProfile | None:
        """
        Use LLM to extract customer insights from full session data.

        The LLM receives all session artifacts (transcript, summary, metrics,
        transport details, participant data, tool usage, etc.) for comprehensive context.
        """
        profile = await self.get_by_profile_id(profile_id)
        if not profile:
            logger.warning(f"Profile {profile_id} not found for AI extraction")
            return None

        try:
            from openai import AsyncOpenAI

            from app.core.config import settings

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            existing_ai_data = profile.ai_extracted_data or {}
            required_fields = ai_required_fields or CUSTOMER_PROFILE_AI_REQUIRED_FIELDS
            required_fields_str = ", ".join(required_fields)
            required_fields_list = "\n".join(
                f"- {field}: (REQUIRED - set to null if not found)" for field in required_fields
            )

            formatted_session_data = self._format_session_data_for_extraction(session_data)

            # IMPORTANT: Exclude DND intent keys from existing data shown to LLM
            # This prevents the LLM from being influenced by previous DND decisions
            # DND should be detected fresh from CURRENT call transcript only
            dnd_intent_keys = ["dnd_intent_telephony_outbound"]
            existing_ai_data_for_prompt = {
                k: v for k, v in existing_ai_data.items() if k not in dnd_intent_keys
            }

            prompt = f"""You are analyzing a complete customer call session to extract useful information for future personalization.

FULL SESSION DATA:
{formatted_session_data}

Call Outcome: {call_outcome or "Not specified"}

Existing AI-extracted data for this customer:
{existing_ai_data_for_prompt if existing_ai_data_for_prompt else "No previous data"}

Your task:
Analyze the full session data above and extract customer information. You MUST include these required fields (set to null if not found):
{required_fields_list}

Additional fields you may include if relevant:
- interests: Topics the customer showed interest in
- communication_style: How the customer prefers to communicate
- follow_up: Any scheduled follow-ups or callbacks
- notes: Any other relevant observations

DND (Do Not Disturb) Detection (CURRENT CALL ONLY):
- dnd_intent_telephony_outbound: Set to true ONLY if the customer explicitly expresses in THIS CURRENT CALL that they don't want to receive outbound calls (e.g., "don't call me", "stop calling", "do not disturb"). Set to false if no such intent is expressed in the current call. DO NOT carry over DND intent from previous calls - evaluate based on THIS call's transcript only.

IMPORTANT:
1. Output ONLY valid JSON (no markdown, no explanation)
2. ALWAYS include required fields: {required_fields_str} (use null if unknown)
3. Extract name from conversation if the customer mentioned it
4. Detect language_preference from the language used in the conversation
5. Look for email/phone in participant data or if mentioned in conversation
6. Merge with existing data - preserve important existing insights
7. Add an \"extracted_at\" timestamp in ISO format

Output a JSON object with extracted/updated data:"""

            response = await client.chat.completions.create(
                model=CUSTOMER_PROFILE_EXTRACTION_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=CUSTOMER_PROFILE_EXTRACTION_LLM_TEMPERATURE,
                max_tokens=CUSTOMER_PROFILE_EXTRACTION_MAX_TOKENS,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning(f"Empty LLM response for AI extraction on profile {profile_id}")
                return profile

            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            try:
                extracted_data = json.loads(content)
            except json.JSONDecodeError as je:
                logger.warning(f"Failed to parse LLM JSON response: {je}")
                return profile

            if not isinstance(extracted_data, dict):
                logger.warning(f"LLM response is not a dict: {type(extracted_data)}")
                return profile

            merged_ai_data = {**existing_ai_data, **extracted_data}

            # Extract DND intents from CURRENT extraction only (not from existing data)
            # DND detection should be based on the CURRENT call transcript, not previous calls
            dnd_intents = {}
            for key in dnd_intent_keys:
                if key in extracted_data:
                    dnd_intents[key] = extracted_data[key]
            
            # ALWAYS remove DND intent keys from merged_ai_data to prevent persistence
            # This ensures old DND intents don't influence future LLM extractions
            for key in dnd_intent_keys:
                merged_ai_data.pop(key, None)

            for field in required_fields:
                if field not in merged_ai_data:
                    merged_ai_data[field] = None

            if "extracted_at" not in merged_ai_data:
                merged_ai_data["extracted_at"] = datetime.datetime.now(datetime.UTC).isoformat()

            # Apply DND intents to profile flags with audit
            now = datetime.datetime.now(datetime.UTC)
            update_fields = {"ai_extracted_data": merged_ai_data, "updated_at": now}

            if any(dnd_intents.values()):  # Only update DND if any intents are true
                # Ensure profile has DND object
                if not profile.dnd:
                    from app.schemas.core.customer_profile import CustomerDnd
                    profile.dnd = CustomerDnd()

                # Apply intents to flags (never unset)
                if dnd_intents.get("dnd_intent_telephony_outbound"):
                    profile.dnd.channels.telephony.outbound = True

                # Update audit information
                profile.dnd.audit.updated_at = now
                profile.dnd.audit.updated_by = "ai_extraction"
                profile.dnd.audit.reason = "customer_opt_out_detected"
                profile.dnd.audit.source_session_id = session_id
                profile.dnd.audit.source_timestamp = now

                update_fields["dnd"] = profile.dnd.model_dump()

            await self.collection.update_one(
                {"_id": profile_id},
                {"$set": update_fields},
            )

            logger.info(
                f"Updated AI-extracted data for profile {profile_id}: keys={list(merged_ai_data.keys())}"
            )
            return await self.get_by_profile_id(profile_id)

        except Exception as e:
            logger.error(f"Failed to extract AI data for profile {profile_id}: {e}")
            return profile

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    async def list_profiles(
        self,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "last_interaction_at",
        sort_order: int = -1,
    ) -> tuple[list[CustomerProfile], int]:
        """List customer profiles with pagination."""
        pipeline = [
            {
                "$facet": {
                    "data": [
                        {"$sort": {sort_by: sort_order}},
                        {"$skip": skip},
                        {"$limit": limit},
                    ],
                    "count": [{"$count": "total"}],
                }
            }
        ]

        result = await self.collection.aggregate(pipeline).to_list(1)
        if not result:
            return [], 0

        profiles_data = result[0]["data"]
        total = result[0]["count"][0]["total"] if result[0]["count"] else 0

        # Apply DND v2 backfill to profiles that need it
        profiles_to_backfill = []
        profiles = []

        for p in profiles_data:
            updated_data, was_changed = self._ensure_dnd_v2(p)
            if was_changed:
                profiles_to_backfill.append(updated_data["_id"])
            profiles.append(CustomerProfile(**updated_data))

        # Bulk backfill any profiles that needed it
        if profiles_to_backfill:
            now = datetime.datetime.now(datetime.UTC)
            from app.schemas.core.customer_profile import CustomerDnd
            default_dnd = CustomerDnd().model_dump()
            await self.collection.update_many(
                {"_id": {"$in": profiles_to_backfill}},
                {"$set": {"dnd": default_dnd, "updated_at": now}}
            )
            logger.debug(f"Backfilled DND v2 structure for {len(profiles_to_backfill)} profiles in list_profiles")

        return profiles, total

    async def search_profiles(self, query: str, limit: int = 10) -> list[CustomerProfile]:
        """Search profiles by name, email, or phone."""
        search_filter = {
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
                {"phone": {"$regex": query, "$options": "i"}},
                {"primary_identifier": {"$regex": query, "$options": "i"}},
            ]
        }

        cursor = self.collection.find(search_filter).limit(limit)
        results = await cursor.to_list(limit)

        # Apply DND v2 backfill to profiles that need it
        profiles_to_backfill = []
        profiles = []

        for p in results:
            updated_data, was_changed = self._ensure_dnd_v2(p)
            if was_changed:
                profiles_to_backfill.append(updated_data["_id"])
            profiles.append(CustomerProfile(**updated_data))

        # Bulk backfill any profiles that needed it
        if profiles_to_backfill:
            now = datetime.datetime.now(datetime.UTC)
            from app.schemas.core.customer_profile import CustomerDnd
            default_dnd = CustomerDnd().model_dump()
            await self.collection.update_many(
                {"_id": {"$in": profiles_to_backfill}},
                {"$set": {"dnd": default_dnd, "updated_at": now}}
            )
            logger.debug(f"Backfilled DND v2 structure for {len(profiles_to_backfill)} profiles in search_profiles")

        return profiles


