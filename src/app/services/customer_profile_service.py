"""
Customer Profile Service for profile resolution and context building.

Resolves profiles at session start, builds context strings for AI prompt
injection, and surfaces language preferences for session configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.managers.customer_profile_manager import CustomerProfileManager
from app.schemas.core.customer_profile import CustomerProfile

if TYPE_CHECKING:
    pass


class CustomerProfileService:
    """Service for customer profile resolution and context building."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.manager = CustomerProfileManager(db)

    async def resolve_profile_for_session(
        self,
        transport_type: str,
        user_phone: str | None = None,
        user_email: str | None = None,
    ) -> CustomerProfile | None:
        """
        Resolve a customer profile based on available identifiers.

        Resolution priority:
        - Telephony (plivo, twilio): phone as primary
        - WebRTC/WebSocket: email as primary
        - Falls back to linked identities
        """
        primary_identifier: str | None
        fallback_identifier: str | None

        if transport_type in ("plivo", "twilio"):
            primary_identifier = user_phone
            fallback_identifier = user_email
        else:
            primary_identifier = user_email
            fallback_identifier = user_phone

        if primary_identifier:
            profile = await self.manager.get_by_identifier(primary_identifier)
            if profile:
                logger.debug(f"Resolved profile {profile.profile_id} via primary identifier: {primary_identifier}")
                return profile

        if fallback_identifier:
            profile = await self.manager.get_by_identifier(fallback_identifier)
            if profile:
                logger.debug(f"Resolved profile {profile.profile_id} via fallback identifier: {fallback_identifier}")
                return profile

        logger.debug(
            f"No profile found for transport={transport_type}, phone={user_phone}, email={user_email}"
        )
        return None

    def get_language_preference(self, profile: CustomerProfile | None) -> str | None:
        """Return language preference from profile (user-set first, then AI-derived)."""
        if profile and profile.language_preference:
            return profile.language_preference
        return None

    def build_profile_context(self, profile: CustomerProfile, include_language_preference: bool = True) -> str:
        """
        Generate a context string for AI system prompt injection.

        Args:
            profile: The customer profile to build context from.
            include_language_preference: If False, excludes language preference from context
                to prevent LLM from automatically switching languages based on profile.

        Includes:
        - Human-provided fields (name, email, phone, language_preference, preferences)
        - AI-extracted data (all keys from ai_extracted_data)
        - Call history (recent summaries, aggregated history)
        """
        sections: list[str] = []
        ai_data = profile.ai_extracted_data or {}

        sections.append("=== CUSTOMER PROFILE ===")
        sections.append("Use these summaries as memory. Do NOT say you cannot remember past conversations; rely on this profile context to personalize answers.")

        customer_name = profile.name or ai_data.get("name")
        if customer_name:
            sections.append(f"Customer Name: {customer_name}")
            sections.append("This is a RETURNING customer - personalize your interaction!")

        if profile.email:
            sections.append(f"Email: {profile.email}")
        if profile.phone:
            sections.append(f"Phone: {profile.phone}")

        # Only include language preference if flag is enabled
        if include_language_preference:
            lang_pref = profile.language_preference or ai_data.get("language_preference")
            if lang_pref:
                sections.append(f"Preferred Language: {lang_pref}")

        if profile.preferences:
            sections.append("\nUser Preferences:")
            for key, value in profile.preferences.items():
                sections.append(f"  - {key}: {value}")

        if ai_data:
            sections.append("\nAI-Extracted Insights:")
            for key, value in ai_data.items():
                # Skip language_preference if flag is disabled, always skip extracted_at
                if key == "extracted_at" or (key == "language_preference" and not include_language_preference):
                    continue
                if isinstance(value, list):
                    formatted = ", ".join(str(v) for v in value)
                elif isinstance(value, dict):
                    formatted = ", ".join(f"{k}: {v}" for k, v in value.items())
                else:
                    formatted = str(value)
                readable_key = key.replace("_", " ").title()
                sections.append(f"  - {readable_key}: {formatted}")

        if profile.total_call_count > 0:
            sections.append(f"\nTotal Previous Calls: {profile.total_call_count}")

            if profile.aggregated_older_summary:
                sections.append("\n--- Historical Context (Older Calls) ---")
                sections.append(profile.aggregated_older_summary)

            if profile.recent_call_summaries:
                sections.append("\n--- Recent Interactions ---")
                for i, summary in enumerate(profile.recent_call_summaries, 1):
                    date_str = summary.timestamp.strftime("%Y-%m-%d")
                    outcome_str = f" [{summary.outcome}]" if summary.outcome else ""
                    sections.append(f"\n{i}. Call on {date_str}{outcome_str}:")
                    sections.append(f"   {summary.summary_text}")

        sections.append("\n=== END CUSTOMER PROFILE ===")
        return "\n".join(sections)

    def build_brief_context(self, profile: CustomerProfile, include_language_preference: bool = True) -> str:
        """Generate a brief context string (shorter version for token efficiency).
        
        Args:
            profile: The customer profile to build context from.
            include_language_preference: If False, excludes language preference from context.
        """
        parts: list[str] = []

        if profile.name:
            parts.append(f"Returning customer: {profile.name}")
        else:
            parts.append("Returning customer")

        if profile.total_call_count > 0:
            parts.append(f"({profile.total_call_count} previous calls)")

        # Only include language preference if flag is enabled
        if include_language_preference and profile.language_preference:
            parts.append(f"Prefers: {profile.language_preference}")

        if profile.recent_call_summaries:
            most_recent = profile.recent_call_summaries[0]
            date_str = most_recent.timestamp.strftime("%Y-%m-%d")
            parts.append(f"Last call ({date_str}): {most_recent.summary_text[:150]}...")

        return " | ".join(parts)

    async def enrich_session_context(
        self,
        transport_type: str,
        user_phone: str | None = None,
        user_email: str | None = None,
    ) -> dict:
        """Resolve profile and return enriched context data."""
        profile = await self.resolve_profile_for_session(
            transport_type=transport_type,
            user_phone=user_phone,
            user_email=user_email,
        )

        if not profile:
            return {
                "profile_found": False,
                "profile": None,
                "language_preference": None,
                "context_string": None,
                "brief_context": None,
            }

        return {
            "profile_found": True,
            "profile": profile,
            "profile_id": profile.profile_id,
            "language_preference": self.get_language_preference(profile),
            "context_string": self.build_profile_context(profile),
            "brief_context": self.build_brief_context(profile),
            "customer_name": profile.name,
            "total_calls": profile.total_call_count,
        }


async def get_customer_profile_context(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    transport_type: str,
    user_phone: str | None = None,
    user_email: str | None = None,
) -> dict:
    """Convenience function to get customer profile context."""
    service = CustomerProfileService(db, tenant_id)
    return await service.enrich_session_context(
        transport_type=transport_type,
        user_phone=user_phone,
        user_email=user_email,
    )


