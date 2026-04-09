import asyncio
import datetime
from typing import Any

import aiohttp
from fastapi import WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.frames.frames import StartFrame, EndFrame, LLMMessagesAppendFrame
from app.utils.transcript_utils import TranscriptAccumulator

from app.agents import BaseAgent
from app.core.pipeline_builder.chat import build_text_pipeline
from app.db.database import get_database, MongoClient
from app.managers.session_manager import SessionManager
from app.managers.artifact_manager import ArtifactManager
from app.managers.log_manager import LogManager
from app.core.observers import (
    MetricsLogger,
    HangupObserver,
    SessionLogObserver,
    SummarizationObserver,
)
from app.schemas.session_schema import SessionState
from app.utils.summary_utils import generate_summary
from pipecat.processors.transcript_processor import TranscriptionMessage
from app.core.constants import IDLE_TIMEOUT_S, RUNNER_SHUTDOWN_TIMEOUT_S

import uuid
from typing import Any

async def ensure_session_exists_for_chat(
    *,
    session_manager: SessionManager,
    session_id: str,
    assistant_id: str,
    overrides_dict: dict | None,
    metadata: dict[str, Any] | None = None,
):
    # Already exists → nothing to do
    session = await session_manager.get_session(session_id)
    if session:
        return session

    # Create (same pattern as Plivo outbound)
    try:
        await session_manager.create_session(
            session_id=session_id,
            assistant_id=assistant_id,
            assistant_overrides=overrides_dict,
            participants=[],          # chat doesn't need phone participants
            created_by=None,          # or fill from auth if you have it
            transport="chat",
            metadata=metadata or {"call_direction": "text"},
        )
    except ValueError:
        # If create_session validates or races with another request,
        # re-fetch and continue.
        pass

    return await session_manager.get_session(session_id)



# Global dict for external artifact saving (same as run_pipeline)
_artifact_managers: dict[str, Any] = {}


class NullPlottingObserver:
    def get_csv_data(self) -> str | None:
        return None


async def run_websocket_text_bot(
    websocket: WebSocket,
    session_id: str,
    tenant_id: str,
    agent: BaseAgent,
    artifact_manager: ArtifactManager,
):
    metadata = {}
    error_details: dict | None = None
    # background_tasks: set[asyncio.Task] = set()
    call_summary: dict | None = None

    aiohttp_session = aiohttp.ClientSession()
    db = get_database(tenant_id, MongoClient.get_client())
    session_manager = SessionManager(db)
    # log_manager = LogManager(db)

    runner = PipelineRunner(handle_sigint=False, force_gc=True)

    task: PipelineTask | None = None
    runner_task: asyncio.Task | None = None
    recv_task: asyncio.Task | None = None

    termination_reason = "session_ended"
    final_state = SessionState.COMPLETED
    transcript_accumulator: TranscriptAccumulator | None = None
    hangup_observer: HangupObserver | None = None
    summarization_observer: SummarizationObserver | None = None
    final_session = None

    try:
        await agent.get_services(aiohttp_session, db=db, tenant_id=tenant_id)

        headers = dict(websocket.headers)
        await agent.set_session_context(
            session_id=session_id,
            transport_name="chat",
            db=db,
            tenant_id=tenant_id,
            provider_session_id=session_id,
            transport_metadata=metadata,
            user_details=None,
            call_data=None,
        )

        pipeline = build_text_pipeline(
            agent=agent,
            websocket=websocket,
            session_id=session_id,
        )
        transcript_accumulator = pipeline.transcript_accumulator  # from pipeline

        metrics_logger = MetricsLogger(pipeline, "chat", session_id)
        session_log_observer = SessionLogObserver("chat", session_id)
        summarization_observer = SummarizationObserver("chat", session_id, transcript_accumulator)
        hangup_observer = HangupObserver(
            session_id=session_id,
            transcript_accumulator=transcript_accumulator,
        ) 

        task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
            observers=[
                metrics_logger,
                session_log_observer,
                summarization_observer,
                hangup_observer,
            ],
        )

        llm = getattr(agent, "_llm", None)
        if llm:
            if hasattr(llm, "_set_task"):
                llm._set_task(task)
            else:
                llm._task = task

        artifact_manager.metrics_logger = metrics_logger
        artifact_manager.session_log_observer = session_log_observer
        artifact_manager.hangup_observer = hangup_observer
        artifact_manager.transcript_accumulator = transcript_accumulator

        _artifact_managers[session_id] = artifact_manager

        runner_task = asyncio.create_task(runner.run(task))
        await task.queue_frames([StartFrame()])

        async def _recv_loop():
            nonlocal termination_reason, final_state, error_details
            while True:
                try:
                    user_text = await asyncio.wait_for(
                        websocket.receive_text(), timeout=IDLE_TIMEOUT_S
                    )

                    transcript_accumulator.add_message(
                        TranscriptionMessage(
                            role="user",
                            content=user_text.strip(),
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                        )
                    )

                    await task.queue_frames([
                        LLMMessagesAppendFrame(
                            [{"role": "user", "content": user_text}],
                            run_llm=True,
                        )
                    ])

                except asyncio.TimeoutError:
                    termination_reason = "idle_timeout"
                    logger.info(f"Idle timeout after {IDLE_TIMEOUT_S}s for {session_id}")
                    if hangup_observer:
                        await hangup_observer.set_reason_idle_timeout()
                    return

                except WebSocketDisconnect:
                    termination_reason = "client_disconnected"
                    logger.info(f"Client disconnected for {session_id}")
                    if hangup_observer:
                        await hangup_observer.set_reason_client_disconnected()
                    return

                except asyncio.CancelledError:
                    raise

                except Exception as e:
                    termination_reason = "error"
                    final_state = SessionState.ERROR
                    error_details = {"error": str(e)}
                    logger.error(f"Error in receive loop: {e}", exc_info=True)
                    return

        recv_task = asyncio.create_task(_recv_loop())
        await recv_task

    except asyncio.CancelledError:
        logger.info(f"Text bot cancelled for {session_id}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in text bot setup: {e}", exc_info=True)
        final_state = SessionState.ERROR
        # error_details = {"error": str(e), "traceback": traceback.format_exc()}
    finally:
        # Push EndFrame first
        if task:
            try:
                await task.queue_frames([EndFrame(reason=termination_reason)])
            except Exception:
                pass

        # Wait for runner to finish
        if runner_task and not runner_task.done():
            try:
                await asyncio.wait_for(runner_task, timeout=RUNNER_SHUTDOWN_TIMEOUT_S)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning(f"Runner timeout – cancelling for {session_id}")
                runner_task.cancel()
                try:
                    await runner_task
                except Exception:
                    pass
        try:
            end_time = (
                hangup_observer.hangup_time
                if hangup_observer and getattr(hangup_observer, "hangup_time", None)
                else datetime.datetime.now(datetime.timezone.utc)
            )

            final_session = await session_manager.end_session(
                session_id=session_id,
                final_state=final_state,
                end_time=end_time,
                save_artifacts=False,
            )

            if not final_session:
                final_session = await session_manager.get_session(session_id)

            logger.info(f"Session {session_id} ended successfully (state: {final_state})")

        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {e}", exc_info=True)
            final_session = await session_manager.get_session(session_id)

              # === Generate and persist summary — STRIP TIMESTAMPS (safe for any accumulator) ===
        try:
            if summarization_observer and final_session:
                raw_messages = summarization_observer.messages or []

                if not raw_messages:
                    logger.info("No messages for summarization — skipping")
                else:
                    # STRIP TIMESTAMPS — this fixes the JSON error forever
                    summary_messages = []
                    for msg in raw_messages:
                        # Handle both dict and TranscriptionMessage objects
                        if isinstance(msg, dict):
                            role = msg.get("role", "user")
                            content = msg.get("text") or msg.get("content", "")
                            # Check for and clean datetime in timestamp
                            if "timestamp" in msg and isinstance(msg["timestamp"], datetime.datetime):
                                msg["timestamp"] = msg["timestamp"].isoformat()
                        else:
                            role = getattr(msg, "role", "user")
                            content = getattr(msg, "content", "") or getattr(msg, "text", "")
                            # Check for and clean datetime in timestamp
                            if hasattr(msg, "timestamp") and isinstance(msg.timestamp, datetime.datetime):
                                msg.timestamp = msg.timestamp.isoformat()
                        summary_messages.append({"role": role, "content": content})

                    logger.debug(f"Prepared {len(summary_messages)} clean messages for summarization (timestamps stripped)")
                    call_summary = await generate_summary(summary_messages, agent.config)

                    if call_summary and not call_summary.get("error"):
                        # Clean the summary object to ensure all datetime objects are converted to strings
                        # Simple cleaning for common cases
                        if isinstance(call_summary, dict):
                            cleaned_summary = {}
                            for key, value in call_summary.items():
                                if isinstance(value, datetime.datetime):
                                    cleaned_summary[key] = value.isoformat()
                                elif isinstance(value, dict):
                                    # Handle nested dicts
                                    nested_cleaned = {}
                                    for nested_key, nested_value in value.items():
                                        if isinstance(nested_value, datetime.datetime):
                                            nested_cleaned[nested_key] = nested_value.isoformat()
                                        else:
                                            nested_cleaned[nested_key] = nested_value
                                    cleaned_summary[key] = nested_cleaned
                                else:
                                    cleaned_summary[key] = value
                            call_summary = cleaned_summary
                        
                        # Safe MongoDB update for metadata: null
                        pipeline = [
                            {"$set": {"metadata": {"$ifNull": ["$metadata", {}]}}},
                            {"$set": {"metadata.call_summary": call_summary}}
                        ]
                        await session_manager.collection.update_one(
                            {"_id": session_id},
                            pipeline
                        )

                        # Update local final_session safely
                        if getattr(final_session, "metadata", None) is None:
                            final_session.metadata = {}
                        final_session.metadata["call_summary"] = call_summary

                        logger.info(f"Summary generated and safely persisted for session {session_id}")
                    else:
                        logger.warning(f"Summary generation failed: {call_summary}")
        except Exception as e:
            logger.warning(f"Error during summarization: {e}", exc_info=True)

        # === Save artifacts with fresh final_session ===
        try:
            if final_session:
                await artifact_manager.save_artifacts(
                    final_session=final_session,
                    agent=agent,
                    initial_metadata=metadata,
                    raw_audio_payload=None,
                    error_details=error_details,
                    
                )
                logger.info(f"Artifacts saved for text session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save artifacts: {e}", exc_info=True)

        # Close websocket
        try:
            await websocket.close(code=1000, reason="Session ended")
        except Exception:
            pass

        # Cleanup services
        for service in [getattr(agent, "_llm", None), getattr(agent, "_context_aggregator", None)]:
            if service and hasattr(service, "cleanup"):
                try:
                    await service.cleanup()
                except Exception:
                    pass

        await aiohttp_session.close()
        _artifact_managers.pop(session_id, None)
        logger.info(f"Text chat session {session_id} fully shut down")


async def websocket_text_endpoint(websocket: WebSocket, session_id: str, tenant_id: str):
    logger.info(f"Text WebSocket connection: session_id={session_id}, tenant_id={tenant_id}")

    try:
        client = MongoClient.get_client()
        db = get_database(tenant_id, client)
        session_manager = SessionManager(db)

       
        assistant_id = websocket.query_params.get("assistant_id") or "default"

        # If you support overrides via query/header, parse them here.
        overrides_dict = None

        # ✅ Create session if it wasn't created earlier
        session = await ensure_session_exists_for_chat(
            session_manager=session_manager,
            session_id=session_id,
            assistant_id=assistant_id,
            overrides_dict=overrides_dict,
            metadata={
                "call_direction": "text",
                "transport_name": "chat",
            },
        )

        if not session:
            logger.warning(f"Unable to create session {session_id}")
            await websocket.close(code=1011, reason="Unable to create session")
            return


        agent_config = await session_manager.get_and_consume_config(
            session_id=session_id,
            transport_name="chat",
            provider_session_id=session_id,
        )
        if not agent_config:
            logger.warning(f"No agent config found for session {session_id}")
            await websocket.close(code=1011, reason="No config available")
            return

        from app.agents import BaseAgent
        from app.schemas.services.agent import PipelineMode

        agent_config.pipeline_mode = PipelineMode.TEXT
        agent = BaseAgent(agent_config=agent_config)

        log_manager = LogManager(db)

        artifact_manager = ArtifactManager(
            session_id=session_id,
            tenant_id=tenant_id,
            transport_name="chat",
            provider_session_id=session_id,
            log_manager=log_manager,
            metrics_logger=None,
            session_log_observer=None,
            hangup_observer=None,
            transcript_accumulator=None,
            plotting_observer=NullPlottingObserver(),
        )

        await run_websocket_text_bot(
            websocket=websocket,
            session_id=session_id,
            tenant_id=tenant_id,
            agent=agent,
            artifact_manager=artifact_manager,
        )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally: {session_id}")
    except Exception as e:
        logger.exception(f"Critical error in text endpoint {session_id}: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
        
        
