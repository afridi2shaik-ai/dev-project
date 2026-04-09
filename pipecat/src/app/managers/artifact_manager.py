"""
Artifact Manager

Manages the generation, saving, and logging of session artifacts.
Separates artifact management concerns from the main transport service.
"""

import asyncio
import datetime
from typing import Any

from loguru import logger

from app.core.config import settings
from app.managers.log_manager import LogManager
from app.schemas.log_schema import Artifact, ArtifactType, LogType, SessionState
from app.schemas.session_schema import Session
from app.utils.audio_utils import save_audio_artifact, save_file_artifact
from app.utils.cost_utils import calculate_cost
from app.utils.summary_utils import generate_summary
from app.utils.transport_utils import get_transport_details_artifact
from app.utils.event_emitter import EventEmitter, EVENTS


class ArtifactManager:
    """A class to manage the generation, saving, and logging of session artifacts."""

    def __init__(
        self,
        session_id: str,
        tenant_id: str,
        transport_name: str,
        provider_session_id: str,
        log_manager: LogManager,
        metrics_logger,
        session_log_observer,
        plotting_observer,
        hangup_observer,
        transcript_accumulator,
    ):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.transport_name = transport_name
        self.provider_session_id = provider_session_id
        self.log_manager = log_manager
        self.metrics_logger = metrics_logger
        self.session_log_observer = session_log_observer
        self.plotting_observer = plotting_observer
        self.hangup_observer = hangup_observer
        self.transcript_accumulator = transcript_accumulator
        self.artifacts: list[Artifact] = []
        self._has_saved = False

    async def save_artifacts(
        self,
        final_session: Session | None,
        agent,
        initial_metadata: dict[str, Any],
        raw_audio_payload: dict[str, Any] | None,
        error_details: dict[str, Any] | None,
    ):
        """Coordinates the generation and saving of all artifacts for the session.
        This is the primary entry point for artifact management.
        """
        if self._has_saved:
            return
        self._has_saved = True

        session_state, duration_seconds = self._get_session_state_and_duration(final_session)

        # --- Artifact Generation Phase ---
        await self._generate_all_artifacts(
            final_session=final_session,
            agent=agent,
            initial_metadata=initial_metadata,
            raw_audio_payload=raw_audio_payload,
            error_details=error_details,
        )

        # --- Database Write Phase ---
        await self.log_manager.save_session_artifacts_log(
            session_id=self.session_id, agent_type=settings.AGENT_TYPE, artifacts=self.artifacts, transport=self.transport_name, session_state=session_state, duration_seconds=duration_seconds, assistant_id=final_session.assistant_id if final_session else None, assistant_name=agent.config.name if agent and agent.config else None, participants=final_session.participants if final_session else []
        )

        # --- Emit session_artifacts_ready event (full Call JSON payload for event-management PATCH) ---
        try:
            logs = await self.log_manager.get_logs_for_session(self.session_id)
            session_artifacts_log = next((log for log in logs if log.log_type == LogType.SESSION_ARTIFACTS), None)
            if session_artifacts_log:
                payload = session_artifacts_log.model_dump(mode="json")
                log_id = getattr(session_artifacts_log, "log_id", None) or payload.get("_id")
                content_count = len(payload.get("content") or [])
                content_types = [a.get("artifact_type") for a in (payload.get("content") or []) if isinstance(a, dict)]
                logger.info(
                    f"Emitting session_artifacts_ready: session_id={self.session_id} | log_id={log_id} | tenant_id={self.tenant_id} | content_artifacts={content_count} | types={content_types}"
                )
                emitter = EventEmitter()
                await emitter.emit_event(EVENTS[2], payload, tenant_id=self.tenant_id)
                logger.info(f"session_artifacts_ready emitted for session_id={self.session_id} (log_id={log_id})")
            else:
                logger.warning(f"No session_artifacts log found for session_id={self.session_id}, skipping session_artifacts_ready emit")
        except Exception as e:
            logger.warning(f"Failed to emit session_artifacts_ready for session {self.session_id}: {e}", exc_info=True)

    def _get_session_state_and_duration(self, final_session: Session | None) -> tuple[SessionState, float | None]:
        """Determines the final session state and duration from the session object.

        Duration Priority:
        1. Provider-reported duration (Twilio CallDuration / Plivo Duration) - most accurate,
           represents actual conversation time from answer to hangup, matches billing
        2. Computed duration (end_time - created_at) - fallback for non-telephony transports
           or if provider callback hasn't arrived yet

        Note: Provider duration is typically shorter than computed duration because it excludes
        WebSocket setup, media negotiation, and teardown time. This is expected and correct.
        """
        if final_session:
            state = final_session.state

            # Prefer provider-reported duration when available
            duration: float | None = None
            try:
                if final_session.metadata and isinstance(final_session.metadata, dict):
                    call_metadata = final_session.metadata.get("call_metadata")
                    if isinstance(call_metadata, dict):
                        provider_duration = call_metadata.get("duration_seconds")
                        if provider_duration is not None:
                            duration = float(provider_duration)
                            logger.debug(f"Using provider duration for session {self.session_id}: {duration}s")
            except Exception:
                # Non-fatal: fall back to computed duration
                duration = None

            # Fallback to computed duration
            if duration is None and final_session.end_time and final_session.created_at:
                end_time = final_session.end_time
                created_at = final_session.created_at

                # Make both timezone-aware if they aren't already
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=datetime.UTC)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.UTC)

                duration = (end_time - created_at).total_seconds()
                logger.debug(f"Using computed duration for session {self.session_id}: {duration}s (provider duration not available)")

            return state, duration

        logger.warning(f"Could not retrieve final session state for {self.session_id}. Logging with ERROR state.")
        return SessionState.ERROR, None

    async def _generate_all_artifacts(self, **kwargs):
        """A helper to run all artifact generation methods concurrently."""
        generation_tasks = [
            self._add_initial_metadata(kwargs.get("initial_metadata")),
            self._save_audio_recording(kwargs.get("raw_audio_payload")),
            self._add_agent_configuration(kwargs.get("agent")),
            self._add_participant_data(kwargs.get("final_session")),
            self._add_observer_artifacts(),
            self._add_summary(kwargs.get("agent")),
            self._add_transport_details(),
            self._add_tool_usage_summary(),
            self._save_session_log(),
            self._save_plotting_csv(),
            self._add_error_details(kwargs.get("error_details")),
            self._add_estimated_cost(),
        ]
        await asyncio.gather(*[task for task in generation_tasks if task is not None])

    def _add_artifact(self, artifact: Artifact | None):
        """Thread-safe method to add an artifact to the list."""
        if artifact:
            self.artifacts.append(artifact)

    async def _add_initial_metadata(self, initial_metadata: dict[str, Any] | None):
        if initial_metadata:
            self._add_artifact(Artifact(artifact_type=ArtifactType.SESSION_METADATA, content={"initial_metadata": initial_metadata}))

    async def _save_audio_recording(self, raw_audio_payload: dict[str, Any] | None):
        if raw_audio_payload:
            try:
                artifact = await save_audio_artifact(self.tenant_id, self.transport_name, self.session_id, raw_audio_payload["audio"], raw_audio_payload["sample_rate"], raw_audio_payload["num_channels"])
                self._add_artifact(artifact)
            except Exception as e:
                logger.error(f"Error saving audio artifact for session {self.session_id}: {e}", exc_info=True)

    async def _add_agent_configuration(self, agent):
        if agent:
            self._add_artifact(Artifact(artifact_type=ArtifactType.AGENT_CONFIGURATION, content=agent.config.model_dump(mode="json")))

    async def _add_participant_data(self, final_session: Session | None):
        if final_session and final_session.participants:
            data = [p.model_dump(mode="json") for p in final_session.participants]
            self._add_artifact(Artifact(artifact_type=ArtifactType.PARTICIPANT_DATA, content={"participants": data}))

    async def _add_observer_artifacts(self):
        # Metrics
        metrics_dict = self.metrics_logger._accumulator.to_dict()
        self._add_artifact(Artifact(artifact_type=ArtifactType.METRICS, content=metrics_dict))

        # Transcript
        transcript_content = self.transcript_accumulator.to_dict()
        self._add_artifact(Artifact(artifact_type=ArtifactType.TRANSCRIPT, content=transcript_content))

        # Hangup Reason
        self._add_artifact(self.hangup_observer.get_hangup_artifact())

    async def _add_summary(self, agent):
        if agent and agent.config.summarization_enabled:
            transcript = self.transcript_accumulator.to_dict().get("messages", [])
            summary = await generate_summary(transcript, agent.config)
            if summary:
                self._add_artifact(Artifact(artifact_type=ArtifactType.SUMMARY, content=summary))

    async def _add_transport_details(self):
        """Fetch transport details, using external credentials if available."""
        from app.managers.phone_number_manager import PhoneNumberManager
        from app.managers.session_manager import SessionManager
        from app.schemas.participant_schema import ParticipantRole

        try:
            # Get session to extract system phone number
            session_manager = SessionManager(self.log_manager.db)
            session = await session_manager.get_session(self.session_id)

            system_phone_number = None
            if session and session.participants:
                # Find system participant's phone number
                for participant in session.participants:
                    if participant.role == ParticipantRole.SYSTEM and participant.phone_number:
                        system_phone_number = participant.phone_number
                        break

            # Get credentials using PhoneNumberManager
            phone_manager = PhoneNumberManager(self.log_manager.db)

            if self.transport_name == "plivo":
                api_key, auth_token = await phone_manager.get_provider_credentials(
                    phone_number=system_phone_number,
                    provider="plivo"
                )
                details = await get_transport_details_artifact(
                    self.transport_name,
                    self.session_id,
                    self.provider_session_id,
                    api_key=api_key,
                    auth_token=auth_token
                )
            elif self.transport_name == "twilio":
                api_key, auth_token = await phone_manager.get_provider_credentials(
                    phone_number=system_phone_number,
                    provider="twilio"
                )
                details = await get_transport_details_artifact(
                    self.transport_name,
                    self.session_id,
                    self.provider_session_id,
                    api_key=api_key,
                    auth_token=auth_token
                )
            else:
                details = None

            self._add_artifact(details)
        except Exception as e:
            logger.error(f"Error fetching transport details for session {self.session_id}: {e}")
            self._add_artifact(None)

    async def _add_tool_usage_summary(self):
        summary = self.transcript_accumulator.get_tool_usage_summary()
        if summary:
            self._add_artifact(Artifact(artifact_type=ArtifactType.TOOL_USAGE, content=summary))

    async def _save_session_log(self):
        if self.session_log_observer:
            contents = self.session_log_observer.accumulator.get_log_contents()
            if contents:
                path = f"vagent/{self.tenant_id}/{self.transport_name}/{self.session_id}/session_log.log"
                await save_file_artifact(self.tenant_id, self.transport_name, self.session_id, contents.encode("utf-8"), "text/plain", "session_log.log")
                self._add_artifact(Artifact(artifact_type=ArtifactType.SESSION_LOG, s3_location=path))

    async def _save_plotting_csv(self):
        csv_data = self.plotting_observer.get_csv_data()
        if csv_data:
            path = f"vagent/{self.tenant_id}/{self.transport_name}/{self.session_id}/metrics.csv"
            await save_file_artifact(self.tenant_id, self.transport_name, self.session_id, csv_data.encode("utf-8"), "text/csv", "metrics.csv")
            self._add_artifact(Artifact(artifact_type=ArtifactType.METRICS_CSV, s3_location=path))

    async def _add_error_details(self, error_details: dict[str, Any] | None):
        if error_details:
            self._add_artifact(Artifact(artifact_type=ArtifactType.ERROR_DETAILS, content=error_details))

    async def _add_estimated_cost(self):
        try:
            cost = calculate_cost(self.metrics_logger._accumulator)
            self._add_artifact(Artifact(artifact_type=ArtifactType.ESTIMATED_COST, content=cost))
        except Exception as e:
            logger.warning(f"Failed to calculate cost estimates: {e}")
