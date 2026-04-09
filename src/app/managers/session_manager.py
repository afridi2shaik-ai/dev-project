import datetime
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.managers.log_manager import LogManager
from app.managers.customer_profile_manager import CustomerProfileManager
from app.schemas import AgentConfig
from app.schemas.log_schema import Artifact, ArtifactType, LogType
from app.schemas.participant_schema import ParticipantDetails
from app.schemas.session_schema import Session, SessionState
from app.schemas.user_schema import UserInfo
from app.utils.config_merge_utils import log_config_merge_details, merge_configs
from app.services.assistant_api_client import AssistantAPIClient, AssistantAPINotFound, AssistantAPIUnauthorized, AssistantAPIError
from app.services.token_provider import TokenProvider
from app.utils.event_emitter import EventEmitter, EVENTS
import aiohttp



class DndBlockedError(ValueError):
    """Raised when a session creation is blocked due to DND settings."""

    def __init__(self, direction: str, policy: str, identifier: str, profile_id: str | None = None):
        self.direction = direction
        self.policy = policy
        self.identifier = identifier
        self.profile_id = profile_id
        super().__init__(f"Session blocked by DND: direction={direction}, policy={policy}, identifier={identifier}")


class SessionManager:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["sessions"]
        self.log_manager = LogManager(db)

    async def create_session(self, session_id: str, assistant_id: str, assistant_overrides: dict[str, Any] | None = None, participants: list[ParticipantDetails] = [], created_by: UserInfo | None = None, transport: str = "pending", provider_session_id: str | None = None, metadata: dict[str, Any] | None = None) -> Session:
        # Validate overrides structure early (without base merge)
        if assistant_overrides:
            try:
                # Create a temporary base to validate basic shape merging (non-strict)
                base_config = AgentConfig()
                log_config_merge_details(base_config, assistant_overrides)
                merge_configs(base_config, assistant_overrides)
            except ValueError as e:
                raise ValueError(f"Assistant overrides are invalid: {e}")

        # Resolve effective agent config for DND enforcement
        # This must happen before session insertion to block if needed
        effective_config = None
        try:
            async with aiohttp.ClientSession() as http:
                async def refresh_tokens() -> tuple[str, str]:
                    return await TokenProvider.get_tokens_for_tenant(self.db.name, force_refresh=True)

                access_token, id_token = await TokenProvider.get_tokens_for_tenant(self.db.name)
                client = AssistantAPIClient()
                base_config = await client.get_config(
                    assistant_id, access_token, id_token, http, on_refresh_tokens=refresh_tokens, tenant_id=self.db.name
                )

                # Merge with overrides to get effective config
                effective_config = merge_configs(base_config, assistant_overrides)
                logger.info(f"✅ Fetched and resolved assistant config for session {session_id} (assistant: {assistant_id})")
        except AssistantAPINotFound:
            logger.warning(f"⚠️ Assistant {assistant_id} not found during session creation for {session_id}. Using fallback defaults.")
        except (AssistantAPIUnauthorized, AssistantAPIError) as e:
            logger.warning(f"⚠️ Assistant API error during session creation for {session_id} (tenant: {self.db.name}): {e}. Using fallback defaults.")
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching assistant config during session creation for {session_id}: {e}", exc_info=True)

        # Fallback to defaults if config fetch failed
        if not effective_config:
            effective_config = AgentConfig()  # Uses default values including enforce_dnd=True, dnd_policy="block_outbound_only"
            if assistant_overrides:
                try:
                    effective_config = merge_configs(effective_config, assistant_overrides)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to merge overrides with fallback config for session {session_id}: {e}")

        # Enforce DND for telephony sessions (raises DndBlockedError if blocked)
        await self._enforce_dnd_for_telephony_session(transport, metadata, participants, effective_config)

        # Create and insert session now that DND enforcement has passed
        now = datetime.datetime.now(datetime.timezone.utc)
        session = Session(
            session_id=session_id,
            agent_type=settings.AGENT_TYPE,
            assistant_id=assistant_id,
            assistant_overrides=assistant_overrides,
            participants=participants,
            created_by=created_by,
            updated_by=created_by,  # On creation, updater is the creator
            transport=transport,
            provider_session_id=provider_session_id,
            metadata=metadata,
            state=SessionState.PREFLIGHT,
            created_at=now,
            updated_at=now,
        )




        await self.collection.insert_one(session.model_dump(by_alias=True))

        # Create initial log entry for this session with PREFLIGHT state (before session_start so log_id exists)
        initial_artifacts = []

        # Add participant data if available
        if created_by or participants:
            participant_artifact_content = {}
            if created_by:
                participant_artifact_content["created_by"] = created_by.model_dump()
            if participants:
                participant_artifact_content["participants"] = [p.model_dump() for p in participants]

            initial_artifacts.append(Artifact(artifact_type=ArtifactType.PARTICIPANT_DATA, content=participant_artifact_content))

        # Add initial metadata if available
        if metadata:
            initial_artifacts.append(Artifact(artifact_type=ArtifactType.SESSION_METADATA, content={"initial_metadata": metadata}))

        # Store the effective config in logs as AGENT_CONFIGURATION artifact
        assistant_name = effective_config.name if effective_config.name else None
        initial_artifacts.append(Artifact(artifact_type=ArtifactType.AGENT_CONFIGURATION, content=effective_config.model_dump()))

        # Save initial log with PREFLIGHT state (includes AGENT_CONFIGURATION if fetch succeeded)
        await self.log_manager.save_session_artifacts_log(
            session_id=session_id,
            agent_type=settings.AGENT_TYPE,
            artifacts=initial_artifacts,
            transport=transport,
            session_state=SessionState.PREFLIGHT,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            participants=participants
        )

        # Resolve log_id for session_start payload (same log doc used later in session_artifacts_ready)
        log_id = None
        try:
            logs = await self.log_manager.get_logs_for_session(session_id)
            session_artifacts_log = next((log for log in logs if log.log_type == LogType.SESSION_ARTIFACTS), None)
            if session_artifacts_log:
                log_id = getattr(session_artifacts_log, "log_id", None) or (session_artifacts_log.model_dump(mode="json").get("_id"))
        except Exception as e:
            logger.warning("Failed to get log_id for session_start for %s: %s", session_id, e)

        # Emit session_start event for event-management microservice (if enabled), including log_id
        try:
            emitter = EventEmitter()
            payload = session.model_dump(mode="json")
            if log_id is not None:
                payload["log_id"] = log_id
            await emitter.emit_event(
                EVENTS[0],
                payload,
                tenant_id=self.db.name,
            )
        except Exception as e:
            logger.warning("Failed to emit session_start event for %s: %s", session_id, e)

        logger.info(f"Created session {session_id} with initial log in PREFLIGHT state" + (f" (config cached)" if effective_config else " (config fetch failed, will retry later)"))
        return session

    async def _get_config_from_logs(self, session_id: str) -> AgentConfig | None:
        """Retrieve assistant config from logs collection if it was previously stored.
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            AgentConfig if found in logs, None otherwise
        """
        try:
            logs = await self.log_manager.get_logs_for_session(session_id)
            if not logs:
                logger.debug(f"No logs found for session {session_id}")
                return None
            
            # Find AGENT_CONFIGURATION artifact in any log entry
            for log in logs:
                if log.content:
                    for artifact in log.content:
                        if artifact.artifact_type == ArtifactType.AGENT_CONFIGURATION and artifact.content:
                            if isinstance(artifact.content, dict):
                                logger.debug(f"✅ Found cached assistant config in logs for session {session_id}")
                                return AgentConfig(**artifact.content)
                            else:
                                logger.warning(f"AGENT_CONFIGURATION artifact content is not a dict for session {session_id}")
            
            logger.debug(f"No AGENT_CONFIGURATION artifact found in logs for session {session_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving config from logs for session {session_id}: {e}", exc_info=True)
            return None

    async def get_session(self, session_id: str) -> Session | None:
        query = {"_id": session_id, "agent_type": settings.AGENT_TYPE}
        data = await self.collection.find_one(query)
        return Session(**data) if data else None

    async def update_session_fields(self, session_id: str, updates: dict[str, Any], updated_by: UserInfo | None = None) -> bool:
        updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
        if updated_by:
            updates["updated_by"] = updated_by.model_dump()

        # Log important state transitions for better visibility
        if "state" in updates:
            logger.info(f"Session {session_id} state transition → {updates['state']}")

        # Log other important field updates
        important_fields = ["transport", "provider_session_id", "end_time"]
        for field in important_fields:
            if field in updates:
                logger.debug(f"Session {session_id} updated: {field} = {updates[field]}")

        # MongoDB accepts dot-notation paths directly; using them prevents us from overwriting
        # entire nested documents (e.g., session metadata) when we only need to flip a flag.
        set_updates = dict(updates)

        query = {"_id": session_id, "agent_type": settings.AGENT_TYPE}
        result = await self.collection.update_one(query, {"$set": set_updates})

        if result.modified_count > 0:
            logger.debug(f"Successfully updated session {session_id} fields")
        else:
            logger.warning(f"No fields were modified for session {session_id} - this might indicate an issue")

        return result.modified_count > 0

    async def get_and_consume_config(self, session_id: str, transport_name: str, provider_session_id: str | None = None) -> AgentConfig | None:
        session = await self.get_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found.")
            return None

        # Try to get config from logs first (cached snapshot from session creation)
        cached_config = await self._get_config_from_logs(session_id)
        
        if cached_config:
            logger.info(f"📦 Using cached assistant config from logs for session {session_id} (no API call needed)")
            # Merge with current overrides in case they changed
            if session.assistant_overrides:
                try:
                    final_config = merge_configs(cached_config, session.assistant_overrides)
                    logger.debug(f"🔧 Merged cached config with session overrides for {session_id}")
                except ValueError as e:
                    logger.error(f"Failed to merge cached config with overrides for session {session_id}: {e}")
                    return None
            else:
                final_config = cached_config
            
            # Update state if needed (only for PREFLIGHT sessions)
            if session.state == SessionState.PREFLIGHT:
                logger.info(f"Session {session_id} state transition → {SessionState.IN_FLIGHT}")
                await self.update_session_fields(session_id, {"state": SessionState.IN_FLIGHT, "transport": transport_name, "provider_session_id": provider_session_id})
                
                # Update log state to IN_FLIGHT (config already exists, just update state)
                await self.log_manager.save_session_artifacts_log(
                    session_id=session_id,
                    agent_type=settings.AGENT_TYPE,
                    artifacts=[Artifact(artifact_type=ArtifactType.AGENT_CONFIGURATION, content=final_config.model_dump())],
                    transport=transport_name,
                    session_state=SessionState.IN_FLIGHT,
                    assistant_id=session.assistant_id,
                    assistant_name=final_config.name,
                    participants=session.participants
                )
                logger.info(f"✅ Log updated to IN_FLIGHT state for session {session_id}")
            else:
                # Just update transport info if needed
                updates = {}
                if transport_name and (not session.transport or session.transport == "pending"):
                    updates["transport"] = transport_name
                if provider_session_id and not session.provider_session_id:
                    updates["provider_session_id"] = provider_session_id
                
                if updates:
                    await self.update_session_fields(session_id, updates)
            
            return final_config

        # Fallback: Config not found in logs, fetch from API (for old sessions or if creation failed)
        logger.warning(f"⚠️ Config not found in logs for session {session_id} (config fetch may have failed during creation). Attempting fallback to Assistant API...")
        
        # If session is already in a final state (COMPLETED, ERROR, etc.), don't change it
        if session.state not in [SessionState.PREFLIGHT]:
            logger.info(f"Session {session_id} already in state {session.state}, retrieving config only (fallback mode).")
            # Fetch latest config from external API without changing state
            try:
                async with aiohttp.ClientSession() as http:
                    async def refresh_tokens() -> tuple[str, str]:
                        return await TokenProvider.get_tokens_for_tenant(self.db.name, force_refresh=True)

                    access_token, id_token = await TokenProvider.get_tokens_for_tenant(self.db.name)
                    client = AssistantAPIClient()
                    base_config = await client.get_config(
                        session.assistant_id, access_token, id_token, http, on_refresh_tokens=refresh_tokens, tenant_id=self.db.name
                    )
                    logger.info(f"✅ Fallback API call succeeded for session {session_id}")
            except AssistantAPINotFound:
                logger.error(f"❌ Fallback failed: Assistant {session.assistant_id} not found for session {session_id}")
                return None
            except (AssistantAPIUnauthorized, AssistantAPIError) as e:
                logger.error(f"❌ Fallback failed: Assistant API error for session {session_id}: {e} (this indicates auth/API issues that also prevented caching during creation)")
                return None
            return merge_configs(base_config, session.assistant_overrides)

        # Fetch base config from external Assistant API (fallback for PREFLIGHT sessions without cached config)
        try:
            async with aiohttp.ClientSession() as http:
                async def refresh_tokens() -> tuple[str, str]:
                    return await TokenProvider.get_tokens_for_tenant(self.db.name, force_refresh=True)

                access_token, id_token = await TokenProvider.get_tokens_for_tenant(self.db.name)
                client = AssistantAPIClient()
                base_config = await client.get_config(
                    session.assistant_id, access_token, id_token, http, on_refresh_tokens=refresh_tokens, tenant_id=self.db.name
                )
                logger.info(f"✅ Fallback API call succeeded for PREFLIGHT session {session_id}")
        except AssistantAPINotFound:
            logger.error(f"❌ Fallback failed: Base assistant config {session.assistant_id} not found for session {session_id}")
            return None
        except (AssistantAPIUnauthorized, AssistantAPIError) as e:
            logger.error(f"❌ Fallback failed: Assistant API error for session {session_id}: {e} (this indicates auth/API issues that also prevented caching during creation)")
            return None

        # Debug tools configuration before merging
        logger.debug(f"🔧 SESSION MANAGER: Base config tools: {base_config.tools}")
        logger.debug(f"🔧 SESSION MANAGER: Session overrides: {session.assistant_overrides}")

        # Merge overrides and update session state
        try:
            final_config = merge_configs(base_config, session.assistant_overrides)
            logger.debug(f"🔧 SESSION MANAGER: Final config tools: {final_config.tools}")

            # Only update state if it's in PREFLIGHT
            if session.state == SessionState.PREFLIGHT:
                logger.info(f"Session {session_id} state transition → {SessionState.IN_FLIGHT}")
                await self.update_session_fields(session_id, {"state": SessionState.IN_FLIGHT, "transport": transport_name, "provider_session_id": provider_session_id})

                # Update the log to reflect IN_FLIGHT state and cache the config (from fallback API call)
                await self.log_manager.save_session_artifacts_log(
                    session_id=session_id,
                    agent_type=settings.AGENT_TYPE,
                    artifacts=[Artifact(artifact_type=ArtifactType.AGENT_CONFIGURATION, content=final_config.model_dump())],
                    transport=transport_name,
                    session_state=SessionState.IN_FLIGHT,
                    assistant_id=session.assistant_id,
                    assistant_name=final_config.name,
                    participants=session.participants
                )
                logger.info(f"✅ Log updated to IN_FLIGHT state for session {session_id} (config cached from fallback API call)")
            else:
                # Just update transport info if needed
                updates = {}
                if transport_name and (not session.transport or session.transport == "pending"):
                    updates["transport"] = transport_name
                if provider_session_id and not session.provider_session_id:
                    updates["provider_session_id"] = provider_session_id

                if updates:
                    await self.update_session_fields(session_id, updates)
        except ValueError as e:
            logger.error(f"Failed to create a valid agent configuration for session {session_id}: {e}")
            return None

        return final_config

    async def update_session_context_summary(self, session_id: str, context_summary: dict[str, Any]) -> bool:
        """Update the session with a summary of the session context."""
        updates = {"context_summary": context_summary}
        return await self.update_session_fields(session_id, updates)

    async def end_session(self, session_id: str, final_state: SessionState = SessionState.COMPLETED, end_time: datetime.datetime | None = None, save_artifacts: bool = False) -> Session | None:
        """End a session with the specified state and end time.
        
        Args:
            session_id: The session to end
            final_state: The final state of the session
            end_time: The actual call end time. If None, uses current time.
                     This should be the time when the call actually ended, not when cleanup completes.
            save_artifacts: Whether to save artifacts immediately (default: False)
                           Set to False to centralize artifact saving in the pipeline's finally block
        
        Returns:
            The updated session, or None if update failed
        """
        # Use provided end_time if available, otherwise use current time
        # This ensures we capture the actual call end time, not the cleanup completion time
        actual_end_time = end_time or datetime.datetime.now(datetime.timezone.utc)

        logger.info(f"Ending session {session_id} with final state: {final_state}, end_time: {actual_end_time.isoformat()}")

        updates = {"end_time": actual_end_time, "state": final_state}
        update_success = await self.update_session_fields(session_id, updates)

        if not update_success:
            logger.error(f"❌ Failed to update session {session_id} state to {final_state} in sessions collection!")
            # Still try to update logs even if sessions update failed
            log_update_success = await self.log_manager.update_session_state(session_id=session_id, new_state=final_state)
            if log_update_success:
                logger.info(f"✅ Updated logs collection for session {session_id} to state {final_state} (but sessions collection update failed)")
            return None

        # Update log session_state as well
        log_update_success = await self.log_manager.update_session_state(session_id=session_id, new_state=final_state)

        if not log_update_success:
            logger.warning(f"⚠️ Session {session_id} updated in sessions collection but failed to update logs collection")

        # Get the updated session
        updated_session = await self.get_session(session_id)
        if not updated_session:
            logger.error(f"❌ Failed to retrieve updated session {session_id} after state change")
            return None

        logger.info(f"✅ Session {session_id} successfully ended with state: {final_state}, end_time: {actual_end_time.isoformat()}")

        # Emit session_end event for event-management microservice (if enabled)
        try:
            emitter = EventEmitter()
            await emitter.emit_event(
                EVENTS[1],
                updated_session.model_dump(mode="json"),
                tenant_id=self.db.name,
            )
        except Exception as e:
            logger.warning("Failed to emit session_end event for %s: %s", session_id, e)

        # Save artifacts immediately after session state changes if requested
        # This is typically set to False to centralize artifact saving in the pipeline's finally block
        if save_artifacts:
            logger.info(f"📦 Saving artifacts immediately after session state change to {final_state} for {session_id}")

            # Initialize artifact tracking if not exists
            if not hasattr(self, "_artifacts_saved_for_session"):
                self._artifacts_saved_for_session = {}

            # Get the artifact manager and save artifacts if possible
            try:
                from app.core.transports.base_transport_service import _save_artifacts_for_session
                await _save_artifacts_for_session(session_id, updated_session)
                self._artifacts_saved_for_session[session_id] = True
                logger.info(f"✅ Artifacts saved immediately for session {session_id}")
            except ImportError:
                logger.warning(f"⚠️ Could not import _save_artifacts_for_session for session {session_id}")
            except Exception as e:
                logger.error(f"❌ Error saving artifacts for session {session_id}: {e}", exc_info=True)

        return updated_session

    def _determine_call_direction(self, metadata: dict[str, Any] | None, participants: list[ParticipantDetails]) -> str:
        """Determine call direction from metadata or participant ordering."""
        # Primary: check metadata.call_direction
        if metadata and "call_direction" in metadata:
            direction = metadata["call_direction"].strip().lower()
            # Normalize outbound-api -> outbound
            if direction == "outbound-api":
                direction = "outbound"
            if direction in ("inbound", "outbound"):
                return direction

        # Fallback: infer from participant ordering
        # SYSTEM first = outbound call, USER first = inbound call
        if participants:
            first_role = participants[0].role
            if first_role == "system":
                return "outbound"
            elif first_role == "user":
                return "inbound"

        # Default to outbound if can't determine
        return "outbound"

    async def _enforce_dnd_for_telephony_session(
        self,
        transport: str,
        metadata: dict[str, Any] | None,
        participants: list[ParticipantDetails],
        effective_config: AgentConfig
    ) -> None:
        """Enforce DND for telephony sessions. Raises DndBlockedError if blocked."""
        # Only enforce for telephony transports
        if transport not in ("twilio", "plivo"):
            return

        # Check if DND enforcement is enabled
        profile_config = effective_config.customer_profile_config
        if not profile_config.enforce_dnd:
            return

        # Determine call direction
        direction = self._determine_call_direction(metadata, participants)

        # Find customer phone identifier from participants
        customer_phone = None
        for participant in participants:
            if participant.role == "user" and participant.phone_number:
                customer_phone = participant.phone_number
                break

        if not customer_phone:
            # No phone identifier found, allow session creation
            return

        # Look up customer profile
        profile_manager = CustomerProfileManager(self.db)
        from app.utils.validation.field_validators import normalize_phone_identifier

        normalized_phone = normalize_phone_identifier(customer_phone) or customer_phone
        profile = await profile_manager.get_by_identifier(normalized_phone)

        if not profile:
            # No profile found, allow session creation
            return

        # Apply DND policy
        policy = profile_config.dnd_policy
        if policy == "ignore":
            return

        # Check if this direction should be blocked
        should_block = False
        if direction == "outbound":
            if policy in ("block_outbound_only", "block_all"):
                should_block = profile.dnd and profile.dnd.channels.telephony.outbound
        elif direction == "inbound":
            if policy in ("block_inbound_only", "block_all"):
                should_block = profile.dnd and profile.dnd.channels.telephony.inbound

        if should_block:
            raise DndBlockedError(
                direction=direction,
                policy=policy,
                identifier=normalized_phone,
                profile_id=profile.profile_id
            )

    async def list_sessions(self, skip: int = 0, limit: int = 20, state: SessionState | None = None) -> tuple[list[Session], int]:
        query = {"agent_type": settings.AGENT_TYPE}
        if state:
            query["state"] = state

        total_count = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        sessions_data = await cursor.to_list(length=limit)
        sessions = [Session(**s) for s in sessions_data]
        return sessions, total_count
