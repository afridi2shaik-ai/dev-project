"""Session Context Service

This service aggregates context information from various sources:
- Transport details (WebRTC, phone calls, etc.)
- User information (JWT tokens, session data)
- Session metadata
- Call/connection details

It provides a unified context that the AI can use to understand:
- How the user is communicating (web, phone, etc.)
- Who the user is (name, email, phone number)
- Session-specific information
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.managers.session_manager import SessionManager
from app.schemas import (
    Session,
    SessionContext,
    TransportContextDetails,
    TransportMode,
    UserContextDetails,
)

if TYPE_CHECKING:
    from app.schemas.services.agent import ContextConfig


class SessionContextService:
    """Service for aggregating and providing session context to the AI."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.session_manager = SessionManager(db)

    async def build_session_context(self, session_id: str, transport_name: str, provider_session_id: str | None = None, user_details: dict[str, Any] | None = None, transport_metadata: dict[str, Any] | None = None, call_data: dict[str, Any] | None = None, context_config: ContextConfig | None = None) -> SessionContext:
        """Build complete session context from available sources.

        Args:
            session_id: The session identifier
            transport_name: Transport mode (webrtc, twilio, plivo, etc.)
            provider_session_id: Provider-specific session ID
            user_details: User details from JWT tokens or auth
            transport_metadata: Transport-specific metadata
            call_data: Call-specific data (for phone calls)
            context_config: Configuration controlling what context to include

        Returns:
            Complete SessionContext object
        """
        try:
            # Import ContextConfig to avoid circular imports
            from app.schemas.services.agent import ContextConfig

            # Use default config if none provided (for backward compatibility)
            if context_config is None:
                context_config = ContextConfig()

            # Get session from database
            session = await self.session_manager.get_session(session_id)
            if not session:
                logger.warning(f"Session {session_id} not found, creating minimal context")
                session = None

            # Build transport context (respects context_config flags)
            transport_context = self._build_transport_context(transport_name=transport_name, provider_session_id=provider_session_id, transport_metadata=transport_metadata, call_data=call_data, session=session, context_config=context_config)

            # Build user context (respects context_config flags)
            user_context = self._build_user_context(user_details=user_details, session=session, call_data=call_data, context_config=context_config)

            # Build conversation metadata (respects context_config flags)
            conversation_metadata = self._build_conversation_metadata(session=session, transport_metadata=transport_metadata, call_data=call_data, context_config=context_config)

            # Get assistant_id from session
            assistant_id = session.assistant_id if session else None

            context = SessionContext(
                session_id=session_id,
                assistant_id=assistant_id,
                transport=transport_context,
                user=user_context,
                conversation_metadata=conversation_metadata
            )

            privacy_mode_msg = " [PRIVACY MODE]" if context_config.privacy_mode else ""
            logger.info(f"Built session context for {session_id}: {transport_context.mode} - {user_context.name or 'anonymous'}{privacy_mode_msg}")
            return context

        except Exception as e:
            logger.error(f"Error building session context for {session_id}: {e}")
            # Return minimal context on error
            return SessionContext(session_id=session_id, transport=TransportContextDetails(mode=TransportMode.WEBSOCKET), user=UserContextDetails(tenant_id=self.tenant_id))

    def _build_transport_context(self, transport_name: str, provider_session_id: str | None, transport_metadata: dict[str, Any] | None, call_data: dict[str, Any] | None, session: Session | None, context_config: ContextConfig | None = None) -> TransportContextDetails:
        """Build transport-specific context."""
        # Map transport names to enum values
        transport_mapping = {
            "webrtc": TransportMode.WEBRTC,
            "twilio": TransportMode.TWILIO,
            "plivo": TransportMode.PLIVO,
            "whatsapp": TransportMode.WHATSAPP,
            "websocket": TransportMode.WEBSOCKET,
            "livekit": TransportMode.LIVEKIT,
        }

        mode = transport_mapping.get(transport_name.lower(), TransportMode.WEBSOCKET)

        context = TransportContextDetails(mode=mode, provider_session_id=provider_session_id)

        # Import ContextConfig for default handling
        from app.schemas.services.agent import ContextConfig

        if context_config is None:
            context_config = ContextConfig()

        # Add phone call specific details (only if transport details are enabled)
        if mode in [TransportMode.TWILIO, TransportMode.PLIVO] and context_config.include_transport_details:
            # Try to extract from structured call_data first
            if call_data:
                logger.debug(f"🔍 Processing call_data for {transport_name}: {call_data}")
                context.call_sid = call_data.get("start", {}).get("callSid") or call_data.get("callId") or call_data.get("callUUID")

                # Extract phone numbers from call data (only if phone numbers are enabled)
                call_details = call_data.get("start", {})
                logger.debug(f"🔍 Call details: {call_details}")
                if context_config.include_phone_numbers:
                    context.from_number = call_details.get("from")
                    context.to_number = call_details.get("to")
                    logger.debug(f"🔍 Extracted phone numbers from call_data: from={context.from_number}, to={context.to_number}")

                # Extract call direction (only if call direction is enabled)
                if context_config.include_call_direction:
                    context.call_direction = call_details.get("direction", "inbound")  # Default to inbound

                # Determine who is calling whom based on direction and our system numbers (only if enabled)
                if context_config.include_phone_numbers or context_config.include_call_direction:
                    from app.core import settings

                    our_system_numbers = [settings.TWILIO_PHONE_NUMBER, settings.PLIVO_PHONE_NUMBER]
                    our_system_numbers = [num for num in our_system_numbers if num]  # Filter out None values

                    if context.call_direction == "inbound":
                        # User called us
                        if context_config.include_phone_numbers:
                            context.user_phone_number = context.from_number
                            context.agent_phone_number = context.to_number
                            logger.debug(f"🔍 INBOUND: user_phone={context.user_phone_number}, agent_phone={context.agent_phone_number}")
                        if context_config.include_call_direction:
                            context.call_initiated_by = "user"
                    elif context.call_direction == "outbound":
                        # We called user
                        if context_config.include_phone_numbers:
                            context.user_phone_number = context.to_number
                            context.agent_phone_number = context.from_number
                        if context_config.include_call_direction:
                            context.call_initiated_by = "agent"
                    # Fallback: try to determine based on our known system numbers
                    elif context_config.include_phone_numbers and context.from_number in our_system_numbers:
                        # We called them (outbound)
                        context.user_phone_number = context.to_number
                        context.agent_phone_number = context.from_number
                        if context_config.include_call_direction:
                            context.call_direction = "outbound"
                            context.call_initiated_by = "agent"
                    elif context_config.include_phone_numbers and context.to_number in our_system_numbers:
                        # They called us (inbound)
                        context.user_phone_number = context.from_number
                        context.agent_phone_number = context.to_number
                        if context_config.include_call_direction:
                            context.call_direction = "inbound"
                            context.call_initiated_by = "user"
                    # Fallback: try to determine based on our known system numbers
                    elif context_config.include_phone_numbers and context.from_number in our_system_numbers:
                        # We called them (outbound)
                        context.user_phone_number = context.to_number
                        context.agent_phone_number = context.from_number
                        if context_config.include_call_direction:
                            context.call_direction = "outbound"
                            context.call_initiated_by = "agent"
                            logger.debug(f"🔍 FALLBACK: Determined OUTBOUND call based on from_number in system numbers: {context.from_number}")
                    elif context_config.include_phone_numbers and context.to_number in our_system_numbers:
                        # They called us (inbound)
                        context.user_phone_number = context.from_number
                        context.agent_phone_number = context.to_number
                        if context_config.include_call_direction:
                            context.call_direction = "inbound"
                            context.call_initiated_by = "user"
                            logger.debug(f"🔍 FALLBACK: Determined INBOUND call based on to_number in system numbers: {context.to_number}")
                    elif context_config.include_phone_numbers:
                        # Can't determine, use raw data
                        context.user_phone_number = context.from_number
                        context.agent_phone_number = context.to_number
                        logger.debug(f"🔍 FALLBACK: Using raw data - user_phone={context.user_phone_number}, agent_phone={context.agent_phone_number}")

            # Fallback: Extract phone numbers from session participants if call_data didn't provide them (only if enabled)
            if context_config.include_phone_numbers and session and session.participants:
                logger.debug(f"Session {session.session_id} has {len(session.participants)} participants")
                system_participant = None
                user_participant = None

                for participant in session.participants:
                    logger.debug(f"Participant: role={participant.role.value}, phone={participant.phone_number}")
                    if participant.role.value == "system":
                        system_participant = participant
                    elif participant.role.value == "user":
                        user_participant = participant

                # If we didn't get phone numbers from call_data, use participants
                if not context.user_phone_number and user_participant and user_participant.phone_number:
                    context.user_phone_number = user_participant.phone_number
                    logger.debug(f"🔍 FALLBACK: Set user phone number from participant: {context.user_phone_number}")

                if not context.agent_phone_number and system_participant and system_participant.phone_number:
                    context.agent_phone_number = system_participant.phone_number
                    logger.debug(f"🔍 FALLBACK: Set agent phone number from participant: {context.agent_phone_number}")

                # Try to determine call direction from our system numbers if not set (only if call direction is enabled)
                if context_config.include_call_direction and not context.call_direction:
                    from app.core import settings

                    our_system_numbers = [settings.PLIVO_PHONE_NUMBER, settings.TWILIO_PHONE_NUMBER]
                    our_system_numbers = [num for num in our_system_numbers if num]  # Filter out None values

                    if context.agent_phone_number in our_system_numbers:
                        # Standard inbound call (user called our system number)
                        context.call_direction = "inbound"
                        context.call_initiated_by = "user"
                        logger.debug(f"🔍 FALLBACK: Determined INBOUND call based on system number: {context.agent_phone_number}")
                    else:
                        # Likely outbound call (we called the user)
                        context.call_direction = "outbound"
                        context.call_initiated_by = "agent"
                        logger.debug(f"🔍 FALLBACK: Determined OUTBOUND call based on system number: {context.agent_phone_number}")
            else:
                logger.debug(f"Session participants not available: session={bool(session)}, participants={len(session.participants) if session else 0}")

        # Add browser/device info for WebRTC (only if browser info is enabled)
        if mode == TransportMode.WEBRTC and transport_metadata and context_config.include_browser_info:
            context.browser_info = {"user_agent": transport_metadata.get("user_agent"), "ip_address": transport_metadata.get("ip_address"), "headers": transport_metadata.get("headers", {})}

        # Apply privacy mode if enabled - mask sensitive information
        if context_config.privacy_mode:
            if hasattr(context, "user_phone_number") and context.user_phone_number:
                context.user_phone_number = context.user_phone_number[:3] + "***" + context.user_phone_number[-3:] if len(context.user_phone_number) > 6 else "***"
            if hasattr(context, "agent_phone_number") and context.agent_phone_number:
                context.agent_phone_number = context.agent_phone_number[:3] + "***" + context.agent_phone_number[-3:] if len(context.agent_phone_number) > 6 else "***"
            if hasattr(context, "from_number") and context.from_number:
                context.from_number = context.from_number[:3] + "***" + context.from_number[-3:] if len(context.from_number) > 6 else "***"
            if hasattr(context, "to_number") and context.to_number:
                context.to_number = context.to_number[:3] + "***" + context.to_number[-3:] if len(context.to_number) > 6 else "***"

        return context

    def _build_user_context(self, user_details: dict[str, Any] | None, session: Session | None, call_data: dict[str, Any] | None, context_config: ContextConfig | None = None) -> UserContextDetails:
        """Build user-specific context."""
        # Import ContextConfig to avoid circular imports
        from app.schemas.services.agent import ContextConfig

        if context_config is None:
            context_config = ContextConfig()

        context = UserContextDetails(tenant_id=self.tenant_id)

        # Debug logging
        logger.debug(f"🎯 Building user context: user_details={user_details}, include_user_details={context_config.include_user_details}")

        # Determine if this is a telephony call (twilio/plivo) vs WebRTC
        # For telephony calls, user_details contains operator info (created_by), not the actual customer
        # We should NOT use operator email in system prompts for telephony calls
        is_telephony_call = call_data is not None or (session and session.transport in ["twilio", "plivo"])

        # Extract user details from JWT/auth data (only if user details are enabled)
        # IMPORTANT: For telephony calls, skip email extraction because user_details contains
        # operator info (created_by), not the actual customer. The customer is identified by phone number.
        if user_details and context_config.include_user_details:
            context.name = user_details.get("name")
            # Only extract email for WebRTC calls, not for telephony (twilio/plivo)
            # For telephony, created_by.email is the operator's email, not the customer's
            if not is_telephony_call:
                context.email = user_details.get("email")
            else:
                logger.debug(f"🎯 Skipping email extraction for telephony call - user_details contains operator info, not customer info")
            context.user_id = user_details.get("sub") or user_details.get("user_id")
            logger.debug(f"🎯 Extracted user context: name={context.name}, email={context.email if not is_telephony_call else '(skipped for telephony)'}, user_id={context.user_id}")
        else:
            logger.debug(f"🎯 No user details extracted: user_details={user_details}, include_user_details={context_config.include_user_details}")

        # Extract phone number from call data first (only if phone numbers are enabled)
        if call_data and context_config.include_phone_numbers:
            call_details = call_data.get("start", {})
            # For phone calls, the user's phone number depends on call direction
            call_direction = call_details.get("direction", "inbound")
            if call_direction == "inbound":
                # User called us, so user's number is the "from" number
                context.phone_number = call_details.get("from")
            elif call_direction == "outbound":
                # We called user, so user's number is the "to" number
                context.phone_number = call_details.get("to")
            else:
                # Default fallback
                context.phone_number = call_details.get("from")

        # Extract user info from session participants (primary source for phone calls)
        if session and session.participants:
            logger.debug(f"Building user context from {len(session.participants)} participants")
            for participant in session.participants:
                logger.debug(f"User context check - participant: role={participant.role.value}, phone={participant.phone_number}, name={participant.name}")
                if participant.role.value == "user":  # User participant (not system)
                    # Extract phone number only if enabled
                    if context_config.include_phone_numbers and participant.phone_number:
                        context.phone_number = participant.phone_number
                        logger.debug(f"Set user phone number from participant: {context.phone_number}")
                    # Extract name only if user details are enabled
                    if context_config.include_user_details and participant.name:
                        context.name = participant.name
                        logger.debug(f"Set user name from participant: {context.name}")
                    break  # Take the first user participant
        else:
            logger.debug("No session participants available for user context")

        # Apply privacy mode if enabled - mask sensitive user information
        if context_config.privacy_mode:
            if context.phone_number:
                context.phone_number = context.phone_number[:3] + "***" + context.phone_number[-3:] if len(context.phone_number) > 6 else "***"
            if context.email:
                email_parts = context.email.split("@")
                if len(email_parts) == 2:
                    username = email_parts[0][:3] + "***" if len(email_parts[0]) > 3 else "***"
                    context.email = username + "@" + email_parts[1]
            if context.name:
                name_parts = context.name.split()
                if len(name_parts) > 1:
                    context.name = name_parts[0] + " " + name_parts[1][0] + "***"
                elif len(name_parts) == 1:
                    context.name = name_parts[0][:2] + "***" if len(name_parts[0]) > 2 else "***"

        return context

    def _build_conversation_metadata(self, session: Session | None, transport_metadata: dict[str, Any] | None, call_data: dict[str, Any] | None, context_config: ContextConfig | None = None) -> dict[str, Any]:
        """Build additional conversation metadata."""
        # Import ContextConfig for default handling
        from app.schemas.services.agent import ContextConfig

        if context_config is None:
            context_config = ContextConfig()

        metadata = {}

        # Add session metadata (basic information always included)
        if session:
            metadata["session_state"] = session.state.value
            metadata["assistant_id"] = session.assistant_id
            metadata["session_created"] = session.created_at.isoformat() if session.created_at else None
            if session.metadata:
                metadata["session_metadata"] = session.metadata

        # Add transport metadata (only if transport details are enabled)
        if transport_metadata and context_config.include_transport_details:
            # Filter sensitive information in privacy mode
            if context_config.privacy_mode and "ip_address" in transport_metadata:
                filtered_metadata = transport_metadata.copy()
                ip = filtered_metadata.get("ip_address", "")
                if ip:
                    ip_parts = ip.split(".")
                    if len(ip_parts) == 4:
                        filtered_metadata["ip_address"] = f"{ip_parts[0]}.{ip_parts[1]}.***.**"
                metadata["transport_metadata"] = filtered_metadata
            else:
                metadata["transport_metadata"] = transport_metadata

        # Add call metadata (only if transport details are enabled)
        if call_data and context_config.include_transport_details:
            call_details = call_data.get("start", {})
            call_metadata = {"account_sid": call_details.get("accountSid"), "call_sid": call_details.get("callSid")}

            # Include direction only if call direction is enabled
            if context_config.include_call_direction:
                call_metadata["direction"] = call_details.get("direction")

            call_metadata["api_version"] = call_details.get("apiVersion")
            metadata["call_metadata"] = call_metadata

        return metadata

    def format_system_prompt_context(self, context: SessionContext, customer_profile=None, include_language_preference: bool = True) -> str:
        """Format session context for inclusion in the system prompt.

        Args:
            context: The session context to format.
            customer_profile: Optional customer profile to include.
            include_language_preference: If False, excludes language preference from profile context
                to prevent LLM from automatically switching languages.

        Returns a natural language description of the session context
        that can be included in the AI's system prompt.
        """
        context_lines = []

        # Add transport context
        greeting_context = context.get_greeting_context()
        if greeting_context and greeting_context != "via voice chat":
            context_lines.append(f"User is connecting {greeting_context}")

        # Add user identification
        reference = context.get_reference_context()
        if reference != "user":
            context_lines.append(f"You can refer to them as: {reference}")

        # Add session timing context
        context_lines.append(f"Session ID: {context.session_id}")
        context_lines.append(f"Session started: {context.session_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Add specific contextual details
        if context.transport.mode == TransportMode.WEBRTC:
            context_lines.append("This is a web-based voice conversation")
        elif context.transport.mode in [TransportMode.TWILIO, TransportMode.PLIVO]:
            # Provide clear phone call context
            if context.transport.call_direction == "inbound":
                context_lines.append("This is an INBOUND phone call - the user called YOU")
                if context.transport.user_phone_number and context.transport.agent_phone_number:
                    context_lines.append(f"User {context.transport.user_phone_number} called your number {context.transport.agent_phone_number}")
                elif context.transport.user_phone_number:
                    context_lines.append(f"User calling from: {context.transport.user_phone_number}")
            elif context.transport.call_direction == "outbound":
                context_lines.append("This is an OUTBOUND phone call - YOU called the user")
                if context.transport.user_phone_number and context.transport.agent_phone_number:
                    context_lines.append(f"You called user at {context.transport.user_phone_number} from your number {context.transport.agent_phone_number}")
                elif context.transport.user_phone_number:
                    context_lines.append(f"You called user at: {context.transport.user_phone_number}")
            else:
                context_lines.append("This is a phone call conversation")
                if context.transport.from_number and context.transport.to_number:
                    context_lines.append(f"Call from {context.transport.from_number} to {context.transport.to_number}")

            # Add call identification context
            if context.transport.call_sid:
                context_lines.append(f"Call ID: {context.transport.call_sid}")

        # Add customer profile context when available
        if customer_profile:
            try:
                from app.services.customer_profile_service import CustomerProfileService

                profile_service = CustomerProfileService(self.db, self.tenant_id)
                brief_context = profile_service.build_brief_context(customer_profile, include_language_preference=include_language_preference)
                full_context = profile_service.build_profile_context(customer_profile, include_language_preference=include_language_preference)
                context_lines.append("Customer profile detected:")
                context_lines.append(brief_context)
                context_lines.append(full_context)
                logger.debug(
                    f"🧩 Session context formatter added customer profile | "
                    f"profile_id={getattr(customer_profile, 'profile_id', None)} "
                    f"name={getattr(customer_profile, 'name', None) or 'unknown'} "
                    f"len={len(full_context)}"
                )
            except Exception as profile_err:
                logger.warning(f"⚠️ Unable to add customer profile context to system prompt: {profile_err}")

        if not context_lines:
            return "No specific session context available."

        return "\n".join(["SESSION CONTEXT:", *[f"- {line}" for line in context_lines]])

    async def get_current_context(self, session_id: str) -> SessionContext | None:
        """Get current context for an active session."""
        try:
            session = await self.session_manager.get_session(session_id)
            if not session:
                return None

            # Rebuild context from session data
            return await self.build_session_context(session_id=session_id, transport_name=session.transport, provider_session_id=session.provider_session_id)
        except Exception as e:
            logger.error(f"Error getting current context for {session_id}: {e}")
            return None

