import json
import uuid
import asyncio
import asyncio
import aiofiles
import plivo
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry import trace
from starlette.responses import HTMLResponse
from fastapi import BackgroundTasks
from fastapi import BackgroundTasks
from app import schemas
from app.agents import BaseAgent
from app.api.dependencies import get_current_user, get_db, get_db_from_request
from app.core import settings
from app.core.constants import (
    WARM_TRANSFER_CONFERENCE_JOIN_DELAY,
    WARM_TRANSFER_HOLD_MUSIC_STOP_DELAY,
)
from app.core.tracing_route import TracingAPIRoute
from app.core.transports.plivo_service import run_plivo_bot
from app.db.database import MongoClient, get_database
from app.managers.session_manager import SessionManager, DndBlockedError
from app.schemas.participant_schema import ParticipantDetails, ParticipantRole
from app.schemas.request_params import PlivoVoiceParams
from app.schemas.telephony_schemas import OutboundCallRequestNoAuth
from app.schemas.user_schema import UserInfo
from app.core.transports.plivo_websocket_manager import plivo_websocket_manager
from datetime import datetime
import base64
from app.managers.phone_number_manager import PhoneNumberManager

tracer = trace.get_tracer(__name__)
plivo_router = APIRouter(route_class=TracingAPIRoute)


async def _speak_to_call(call_uuid: str, message: str) -> None:
    """Speak a short message on a Plivo leg."""
    if not call_uuid:
        return

    def _speak():
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        client.calls.speak(
            call_uuid=call_uuid,
            text=message,
            voice="WOMAN",
            language="en-US",
        )

    try:
        await asyncio.to_thread(_speak)
        logger.info(f"Spoke message on call {call_uuid}")
    except Exception as exc:
        logger.warning(f"Failed to speak message on call {call_uuid}: {exc}")


async def _hangup_call(call_uuid: str) -> None:
    """Hang up a specific Plivo leg."""
    if not call_uuid:
        return

    def _hangup():
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        client.calls.hangup(call_uuid)

    try:
        await asyncio.to_thread(_hangup)
        logger.info(f"Requested hangup for call {call_uuid}")
    except Exception as exc:
        logger.warning(f"Failed to hang up call {call_uuid}: {exc}")


async def _stop_playing(call_uuid: str) -> None:
    """Stop any audio/hold music playing on a specific Plivo call.
    
    This should be called before speaking a message to ensure the customer
    can clearly hear the message without background audio interference.
    """
    if not call_uuid:
        return

    def _stop():
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        client.calls.stop_playing(call_uuid)

    try:
        await asyncio.to_thread(_stop)
        logger.info(f"Stopped audio playback for call {call_uuid}")
    except Exception as exc:
        logger.warning(f"Failed to stop audio playback for call {call_uuid}: {exc}")


async def _speak_to_conference_member(conference_name: str, member_id: str, message: str) -> bool:
    """Speak a message to a specific conference member using Plivo conference API.
    
    This is required when a call is in a conference - regular call.speak() doesn't work.
    
    Args:
        conference_name: The name of the conference room
        member_id: The member ID or 'all' to speak to all members
        message: The text message to speak
        
    Returns:
        True if successful, False otherwise
    """
    if not conference_name or not message:
        return False

    def _speak():
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        return client.conferences.member_speak(
            conference_name=conference_name,
            member_id=member_id,
            text=message,
            voice="WOMAN",
            language="en-US",
        )

    try:
        response = await asyncio.to_thread(_speak)
        logger.info(f"Spoke message to conference {conference_name} member {member_id}: {response}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to speak to conference {conference_name} member {member_id}: {exc}")
        return False


async def _hangup_conference_member(conference_name: str, member_id: str) -> bool:
    """Hang up a specific member in a conference.
    
    Args:
        conference_name: The name of the conference room
        member_id: The member ID or 'all' to hang up all members
        
    Returns:
        True if successful, False otherwise
    """
    if not conference_name:
        return False

    def _hangup():
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        return client.conferences.member_hangup(
            conference_name=conference_name,
            member_id=member_id,
        )

    try:
        response = await asyncio.to_thread(_hangup)
        logger.info(f"Hung up conference {conference_name} member {member_id}: {response}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to hang up conference {conference_name} member {member_id}: {exc}")
        return False


async def _handle_supervisor_disconnect(
    session_manager: SessionManager,
    session_id: str,
    original_call_uuid: str | None,
    metadata: dict[str, Any],
    disconnect_reason: str,
    tenant_id: str | None = None,
) -> None:
    from app.services.warm_transfer_service import handle_supervisor_disconnect

    await handle_supervisor_disconnect(
        session_manager=session_manager,
        session_id=session_id,
        original_call_uuid=original_call_uuid,
        metadata=metadata,
        disconnect_reason=disconnect_reason,
        speak_to_call_func=_speak_to_call,
        hangup_call_func=_hangup_call,
        speak_to_conference_func=_speak_to_conference_member,
        hangup_conference_member_func=_hangup_conference_member,
        stop_playing_func=_stop_playing,
        tenant_id=tenant_id,
    )


@plivo_router.post("/inbound", response_class=HTMLResponse)
async def inbound_call(request: Request, db: AsyncIOMotorDatabase = Depends(get_db_from_request)):
    with tracer.start_as_current_span("inbound_call_handler"):
        form = await request.form()
        call_uuid = form.get("CallUUID")

        inbound_call_details = dict(form)

        base_url = request.base_url
        tenant_id = db.name

        logger.info(f"📞 Plivo inbound call received: call_uuid={call_uuid}, tenant_id={tenant_id}, base_url={base_url}")

        session_manager = SessionManager(db)

        # Check if this is an outbound call being answered vs. a new inbound call
        session_id = request.query_params.get("session_id")

        if session_id:
            # This is an outbound call that has been answered
            # For outbound calls, "From" is our system number (the one making the call)
            # "To" is the customer number (the one we called)
            system_phone_number = form.get("From")
            logger.info(f"Received inbound webhook for existing outbound session: {session_id}")
            
            # Get credentials based on system phone number (external or default)
            phone_manager = PhoneNumberManager(db)
            auth_id, auth_token = await phone_manager.get_provider_credentials(
                phone_number=system_phone_number,
                provider="plivo"
            )
            
            await session_manager.update_session_fields(session_id, {
                "provider_session_id": call_uuid, 
                "metadata.inbound_http_request": inbound_call_details,
                "metadata.base_url": base_url.__str__(),
                "metadata.provider_credentials": {"auth_id": auth_id, "provider": "plivo"}
            })
        else:
            # This is a new inbound call
            # For inbound calls, "To" is our system number (the one receiving the call)
            # "From" is the customer number (the one calling us)
            to_number = form.get("To")
            
            # Get credentials based on phone number (external or default) for inbound calls
            # This ensures any API operations later use the correct credentials
            phone_manager = PhoneNumberManager(db)
            auth_id, auth_token = await phone_manager.get_provider_credentials(
                phone_number=to_number,
                provider="plivo"
            )
            
            logger.info("Received new inbound call. Creating a new session.")
            assistant_id = request.query_params.get("assistant_id", "default")

            participants = [ParticipantDetails(role=ParticipantRole.SYSTEM, phone_number=to_number), ParticipantDetails(role=ParticipantRole.USER, phone_number=form.get("From"))]

            session_id = str(uuid.uuid4())
            try:
                await session_manager.create_session(
                    session_id=session_id,
                    assistant_id=assistant_id,
                    participants=participants,
                    transport="plivo",
                    provider_session_id=call_uuid,
                    metadata={
                        "inbound_http_request": inbound_call_details, 
                        "base_url": str(base_url), 
                        "call_direction": "inbound",
                        "provider_credentials": {"auth_id": auth_id, "provider": "plivo"}
                    },
                )
            except DndBlockedError as e:
                logger.warning(f"🚫 Inbound Plivo call blocked by DND for {e.identifier}: direction={e.direction}, policy={e.policy}")
                return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

        wss_url = f"wss://{base_url.hostname}/vagent/api/plivo/voice/{call_uuid}?session_id={session_id}&tenant_id={tenant_id}"

        logger.info(f"🔗 Plivo WebSocket URL: {wss_url}")

        # Escape the URL for XML
        xml_safe_wss_url = wss_url.replace("&", "&amp;")

        async with aiofiles.open("src/app/templates/plivo_streams.xml") as f:
            xml_content = (await f.read()).replace("{{WSS_URL}}", xml_safe_wss_url)

        logger.info(f"✅ Plivo inbound call response generated for call_uuid={call_uuid}, session_id={session_id}")
        return HTMLResponse(content=xml_content, media_type="application/xml")


@plivo_router.websocket("/voice/{call_id}")
async def voice(websocket: WebSocket, params: PlivoVoiceParams = Depends()):
    with tracer.start_as_current_span("plivo_websocket_handler"):
        await websocket.accept()
        session_id = None
        pipeline_task = None
        try:
            session_id = websocket.query_params.get("session_id")
            tenant_id = websocket.query_params.get("tenant_id")
            if not session_id or not tenant_id:
                logger.error("session_id and tenant_id are required in WebSocket URL")
                await websocket.close(code=1008)
                return

            # Register WebSocket connection for warm transfer
            if session_id:
                plivo_websocket_manager.add_connection(session_id, websocket, call_uuid=params.call_id)
                logger.info(f"✅ Registered WebSocket for session {session_id}")

            client = MongoClient.get_client()
            if tenant_id not in await client.list_database_names():
                logger.warning(f"Attempted access to non-existent tenant database: {tenant_id}")
                await websocket.close(code=1008)
                return

            db = get_database(tenant_id, client)
            session_manager = SessionManager(db)

            # Check if warm transfer is active BEFORE starting bot pipeline
            session = await session_manager.get_session(session_id)
            warm_transfer_active = False
            original_call_uuid = session.provider_session_id

            if session and session.metadata:
                metadata = session.metadata if isinstance(session.metadata, dict) else session.metadata.__dict__ if hasattr(session.metadata, '__dict__') else {}
                warm_transfer_active = metadata.get('warm_transfer_active', False)
                original_call_uuid = metadata.get('original_call_uuid')

            # If warm transfer is active and this is the original caller, the WebSocket should be closed soon (handled in conference_join), Just continue with normal bot flow until it's closed
            if warm_transfer_active and params.call_id == original_call_uuid:
                timestamp = datetime.now().isoformat()
                logger.info(f"[{timestamp}] 🔍 Warm transfer active - original caller WebSocket will be closed soon")

            agent_config = await session_manager.get_and_consume_config(session_id=session_id, transport_name="plivo", provider_session_id=params.call_id)
            if not agent_config:
                logger.error(f"No session data or config found for session_id: {session_id}")
                await websocket.close()
                return

            start_data = websocket.iter_text()
            start_message = json.loads(await start_data.__anext__())

            logger.info(f"Plivo Start Message: {start_message}")

            start_info = start_message.get("start", {})
            stream_id = start_info.get("streamId")

            if not stream_id:
                logger.error("No streamId found in start message")
                await websocket.close()
                return

            logger.info(f"WebSocket connection accepted for stream: {stream_id}, call: {params.call_id}")
            agent = BaseAgent(agent_config=agent_config)

            # Run bot pipeline in a task so we can cancel it if needed
            async def run_bot():
                await run_plivo_bot(websocket, stream_id, params.call_id, session_id, tenant_id, agent, start_message)

            pipeline_task = asyncio.create_task(run_bot())
            plivo_websocket_manager.set_pipeline_task(session_id, pipeline_task)

            # Wait for pipeline to complete
            await pipeline_task

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            if session_id:
                await plivo_websocket_manager.cancel_pipeline_task(session_id)
                plivo_websocket_manager.remove_connection(session_id)
        except asyncio.CancelledError:
            logger.info(f"Pipeline cancelled for session {session_id}")
            if session_id:
                plivo_websocket_manager.remove_connection(session_id)
            if session_id:
                await plivo_websocket_manager.cancel_pipeline_task(session_id)
                plivo_websocket_manager.remove_connection(session_id)
        except asyncio.CancelledError:
            logger.info(f"Pipeline cancelled for session {session_id}")
            if session_id:
                plivo_websocket_manager.remove_connection(session_id)
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
            if session_id:
                await plivo_websocket_manager.cancel_pipeline_task(session_id)
            logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
            if session_id:
                await plivo_websocket_manager.cancel_pipeline_task(session_id)
            await websocket.close()


@plivo_router.post("/outbound-call", response_model=schemas.OutboundCallResponse)
async def outbound_call(request: Request, data: schemas.OutboundCallRequest, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    with tracer.start_as_current_span("outbound_call_handler"):
        base_url = request.base_url

        session_manager = SessionManager(db)
        assistant_id = data.assistant_id or "default"
        from_number = data.from_number or settings.PLIVO_PHONE_NUMBER
                
        phone_manager = PhoneNumberManager(db)
        auth_id, auth_token = await phone_manager.get_provider_credentials(
            phone_number=from_number,
            provider="plivo"
        )
        client = plivo.RestClient(auth_id, auth_token)

        # Create participant details
        participants = []
        participants.append(ParticipantDetails(role=ParticipantRole.SYSTEM, phone_number=from_number))

        user_name = None
        # Extract user name from the validated overrides if they exist
        if data.assistant_overrides and data.assistant_overrides.customer_details:
            user_name = data.assistant_overrides.customer_details.name
        participants.append(ParticipantDetails(role=ParticipantRole.USER, phone_number=data.to, name=user_name))

        # Extract a clean dict of just the provided overrides
        overrides_dict = data.assistant_overrides.model_dump(exclude_unset=True) if data.assistant_overrides else None

        # Create user info for auditing
        user_info = UserInfo(id=current_user.get("sub"), name=current_user.get("name"), email=current_user.get("email"), role=current_user.get("role"))

        # Get tenant_id from the database name, which is derived from the token
        tenant_id = db.name
        session_id = str(uuid.uuid4())

        # Check for DND blocking before proceeding
        try:
            # Store call direction in metadata for proper direction detection
            metadata = {"call_direction": "outbound", "base_url": str(base_url)}
            await session_manager.create_session(session_id=session_id, assistant_id=assistant_id, assistant_overrides=overrides_dict, participants=participants, created_by=user_info, transport="plivo", metadata=metadata)
        except DndBlockedError as e:
            logger.warning(f"🚫 Outbound Plivo call blocked by DND for {e.identifier}: direction={e.direction}, policy={e.policy}")
            detail = f"Call blocked by Do Not Disturb settings. Direction: {e.direction}, Policy: {e.policy.replace('_', ' ').title()}, Phone: {e.identifier}"
            raise HTTPException(status_code=403, detail=detail)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        await session_manager.update_session_fields(
            session_id,
            {"metadata.base_url": str(base_url)}
        )
        answer_url = f"https://{base_url.hostname}/vagent/api/plivo/inbound?session_id={session_id}&tenant_id={tenant_id}"
        hangup_url = f"https://{base_url.hostname}/vagent/api/plivo/hangup?session_id={session_id}&tenant_id={tenant_id}"

        logger.info(f"📞 Plivo outbound call: session_id={session_id}, to={data.to}, from={from_number}")
        logger.info(f"🔗 Plivo answer_url: {answer_url}")
        logger.info(f"🔗 Plivo hangup_url: {hangup_url}")

        try:
            response = client.calls.create(
                from_=from_number,
                to_=data.to,
                answer_url=answer_url,
                answer_method="POST",
                hangup_url=hangup_url,
                hangup_method="POST",
            )
            logger.info(f"✅ Plivo call initiated: call_uuid={response.request_uuid}, session_id={session_id}")
            return {"message": "Call initiated", "call_id": response.request_uuid, "session_id": session_id}
        except Exception as e:
            logger.error(f"Error making outbound call: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@plivo_router.post("/outbound-call-noauth", response_model=schemas.OutboundCallResponse, include_in_schema=False, summary="Create Outbound Call (No Auth)")
async def outbound_call_noauth(
    request: Request,
    data: OutboundCallRequestNoAuth,
):
    """
    Initiates an outbound call to a specified phone number without requiring user authentication.
    This endpoint is intended for use in backend systems or scenarios where user context is not available.
    The tenant under which the call should be made must be specified in the request body.
    """
    tenant_id = data.tenant_id
    client = MongoClient.get_client()
    if tenant_id not in await client.list_database_names():
        raise HTTPException(status_code=403, detail="Forbidden: Invalid tenant.")
    db = get_database(tenant_id, client)

    with tracer.start_as_current_span("outbound_call_noauth_handler"):
        try:
            base_url = request.base_url

            session_manager = SessionManager(db)
            assistant_id = data.assistant_id or "default"
            from_number = data.from_number or settings.PLIVO_PHONE_NUMBER

            # Get credentials based on phone number (external or default)
            phone_manager = PhoneNumberManager(db)
            auth_id, auth_token = await phone_manager.get_provider_credentials(
                phone_number=from_number,
                provider="plivo"
            )
            client = plivo.RestClient(auth_id, auth_token)

            # Create participant details
            participants = []
            participants.append(ParticipantDetails(role=ParticipantRole.SYSTEM, phone_number=from_number))

            user_name = None
            if data.assistant_overrides and data.assistant_overrides.customer_details:
                user_name = data.assistant_overrides.customer_details.name
            participants.append(ParticipantDetails(role=ParticipantRole.USER, phone_number=data.to, name=user_name))

            # Extract a clean dict of just the provided overrides
            overrides_dict = data.assistant_overrides.model_dump(exclude_unset=True) if data.assistant_overrides else None

            session_id = str(uuid.uuid4())
            try:
                # Store call direction in metadata for proper direction detection
                metadata = {"call_direction": "outbound"}
                await session_manager.create_session(session_id=session_id, assistant_id=assistant_id, assistant_overrides=overrides_dict, participants=participants, created_by=None, transport="plivo", metadata=metadata)
            except DndBlockedError as e:
                logger.warning(f"🚫 Outbound Plivo call (noauth) blocked by DND for {e.identifier}: direction={e.direction}, policy={e.policy}")
                detail = f"Call blocked by Do Not Disturb settings. Direction: {e.direction}, Policy: {e.policy.replace('_', ' ').title()}, Phone: {e.identifier}"
                raise HTTPException(status_code=403, detail=detail)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            answer_url = f"https://{base_url.hostname}/vagent/api/plivo/inbound?session_id={session_id}&tenant_id={tenant_id}"
            hangup_url = f"https://{base_url.hostname}/vagent/api/plivo/hangup?session_id={session_id}&tenant_id={tenant_id}"

            logger.info(f"📞 Plivo outbound call (no-auth): session_id={session_id}, to={data.to}, from={from_number}")
            logger.info(f"🔗 Plivo answer_url: {answer_url}")
            logger.info(f"🔗 Plivo hangup_url: {hangup_url}")

            response = client.calls.create(
                from_=from_number,
                to_=data.to,
                answer_url=answer_url,
                answer_method="POST",
                hangup_url=hangup_url,
                hangup_method="POST",
            )
            logger.info(f"✅ Plivo call initiated (no-auth): call_uuid={response.request_uuid}, session_id={session_id}")
            return {"message": "Call initiated", "call_id": response.request_uuid, "session_id": session_id}
        except Exception as e:
            logger.error(f"Error making outbound call (no-auth): {e}")
            raise HTTPException(status_code=500, detail=str(e))


@plivo_router.post("/hangup", response_class=HTMLResponse)
@plivo_router.get("/hangup", response_class=HTMLResponse)
async def hangup(request: Request):
    """
    Plivo hangup callback handler with enhanced session state management.

    Receives hangup events from Plivo and updates session state based on call outcome.
    Maps Plivo HangupCause codes to appropriate SessionState values.
    Supports both GET and POST methods for compatibility with different Plivo webhook configurations.

    Key Plivo Parameters:
    - CallUUID: Unique call identifier
    - HangupCause: Reason for hangup (e.g., "NORMAL_CLEARING", "USER_BUSY", "NO_ANSWER")
    - CallStatus: Current call status
    - Duration: Call duration in seconds
    """
    with tracer.start_as_current_span("plivo_hangup_handler"):
        # Support both GET (query params) and POST (form data) methods
        if request.method == "GET":
            data_dict = dict(request.query_params)
        else:
            data = await request.form()
            data_dict = dict(data)

        call_uuid = data_dict.get("CallUUID", "")
        call_status = data_dict.get("CallStatus", "")
        hangup_cause = data_dict.get("HangupCause", "")
        duration = data_dict.get("Duration", "0")

        logger.info(f"Plivo hangup callback: call_uuid={call_uuid}, call_status={call_status}, hangup_cause={hangup_cause}, duration={duration}")

        # Extract session info from query parameters if available
        session_id = request.query_params.get("session_id")
        tenant_id = request.query_params.get("tenant_id")

        if session_id and tenant_id:
            try:
                # Get database
                client = MongoClient.get_client()
                if tenant_id not in await client.list_database_names():
                    logger.warning(f"Tenant database not found: {tenant_id}")
                    return HTMLResponse(content="<Response></Response>", media_type="application/xml")

                db = get_database(tenant_id, client)
                session_manager = SessionManager(db)

                # Get current session
                current_session = await session_manager.get_session(session_id)
                if not current_session:
                    logger.warning(f"Session {session_id} not found for Plivo hangup callback.")
                    return HTMLResponse(content="<Response></Response>", media_type="application/xml")

                session_metadata: dict[str, Any] = {}
                if current_session.metadata:
                    if isinstance(current_session.metadata, dict):
                        session_metadata = current_session.metadata.copy()
                    elif hasattr(current_session.metadata, "model_dump"):
                        session_metadata = current_session.metadata.model_dump()
                    elif hasattr(current_session.metadata, "__dict__"):
                        session_metadata = dict(current_session.metadata.__dict__)

                original_call_uuid = session_metadata.get("original_call_uuid") or getattr(current_session, "provider_session_id", None)
                supervisor_call_uuid = session_metadata.get("supervisor_call_uuid")

                supervisor_disconnect_reason = None
                is_supervisor_leg = False
                is_customer_leg = False
                warm_transfer_active = session_metadata.get("warm_transfer_active", False)

                if supervisor_call_uuid:
                    is_supervisor_leg = call_uuid == supervisor_call_uuid
                elif original_call_uuid and call_uuid and call_uuid != original_call_uuid:
                    is_supervisor_leg = True

                supervisor_phone = session_metadata.get("supervisor_phone_number")
                if original_call_uuid and call_uuid == original_call_uuid:
                    if supervisor_call_uuid or supervisor_phone:
                        is_customer_leg = True
                        logger.info(
                            "Customer (original caller) disconnected: call_uuid=%s, supervisor_call_uuid=%s, supervisor_phone=%s",
                            call_uuid,
                            supervisor_call_uuid,
                            supervisor_phone,
                        )
                        if not supervisor_call_uuid and supervisor_phone:
                            logger.warning(
                                "Customer disconnected but supervisor_call_uuid missing. Cannot notify; supervisor phone=%s",
                                supervisor_phone,
                            )
                    else:
                        logger.debug(
                            "Original caller disconnected but no supervisor info found. call_uuid=%s, original_call_uuid=%s",
                            call_uuid,
                            original_call_uuid,
                        )

                # Handle empty call_uuid case during active warm transfer
                # When call_uuid is empty but warm transfer is active, assume supervisor leg disconnected
                if not call_uuid and warm_transfer_active and (supervisor_call_uuid or supervisor_phone):
                    logger.warning(
                        f"Empty call_uuid during active warm transfer. Assuming supervisor disconnect. "
                        f"supervisor_call_uuid={supervisor_call_uuid}, supervisor_phone={supervisor_phone}"
                    )
                    is_supervisor_leg = True
                    # Determine reason based on hangup_cause or default to no_answer
                    if hangup_cause in {"USER_BUSY", "CALL_REJECTED"}:
                        supervisor_disconnect_reason = "busy"
                    elif hangup_cause in {"NO_ANSWER", "ORIGINATOR_CANCEL"} or not hangup_cause:
                        supervisor_disconnect_reason = "no_answer"
                    else:
                        supervisor_disconnect_reason = "ended"

                if is_supervisor_leg:
                    # Only set disconnect reason if not already set (e.g., from empty call_uuid handler)
                    if not supervisor_disconnect_reason:
                        if hangup_cause in {"USER_BUSY", "CALL_REJECTED"}:
                            supervisor_disconnect_reason = "busy"
                        elif hangup_cause in {"NO_ANSWER", "ORIGINATOR_CANCEL"}:
                            supervisor_disconnect_reason = "no_answer"
                        else:
                            supervisor_disconnect_reason = "ended"

                    await _handle_supervisor_disconnect(
                        session_manager=session_manager,
                        session_id=session_id,
                        original_call_uuid=original_call_uuid,
                        metadata=session_metadata,
                        disconnect_reason=supervisor_disconnect_reason,
                        tenant_id=tenant_id,
                    )
                elif is_customer_leg and supervisor_call_uuid:
                    from app.services.warm_transfer_service import handle_customer_disconnect

                    await handle_customer_disconnect(
                        session_manager=session_manager,
                        session_id=session_id,
                        supervisor_call_uuid=supervisor_call_uuid,
                        metadata=session_metadata,
                        speak_to_call_func=_speak_to_call,
                        hangup_call_func=_hangup_call,
                        tenant_id=tenant_id,
                    )

                # Determine new session state based on hangup cause
                import datetime

                from app.schemas.session_schema import SessionState

                new_state = current_session.state
                duration_int = int(duration) if duration.isdigit() else 0

                if hangup_cause in {"NO_ANSWER", "ORIGINATOR_CANCEL"}:
                    new_state = SessionState.MISSED_CALL
                    logger.warning(f"Session {session_id}: Call not answered by user (cause: {hangup_cause})")
                elif hangup_cause in {"USER_BUSY", "CALL_REJECTED"}:
                    new_state = SessionState.BUSY
                    logger.info(f"Session {session_id}: User was busy or rejected call (cause: {hangup_cause})")
                elif hangup_cause in {"UNALLOCATED_NUMBER", "INVALID_NUMBER_FORMAT", "NETWORK_OUT_OF_ORDER"}:
                    new_state = SessionState.FAILED
                    logger.error(f"Session {session_id}: Call failed (cause: {hangup_cause})")
                elif duration_int > 0 and hangup_cause == "NORMAL_CLEARING":
                    new_state = SessionState.COMPLETED
                    logger.info(f"Session {session_id}: Call completed normally (duration: {duration}s)")
                elif duration_int == 0:
                    new_state = SessionState.MISSED_CALL
                    logger.warning(f"Session {session_id}: Call ended with no duration (cause: {hangup_cause})")

                if new_state != current_session.state:
                    call_metadata = {
                        "provider": "plivo",
                        "call_uuid": call_uuid,
                        "call_status": call_status,
                        "hangup_cause": hangup_cause,
                        "duration_seconds": duration_int,
                        "hangup_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    }

                    await session_manager.update_session_fields(
                        session_id,
                        updates={"state": new_state, "metadata.call_metadata": call_metadata},
                    )
                    logger.info(f"Plivo Call {call_uuid} for session {session_id} updated to state: {new_state}")

                    from app.managers.log_manager import LogManager

                    log_manager = LogManager(db)
                    try:
                        await log_manager.update_session_state(
                            session_id=session_id,
                            new_state=new_state,
                            duration_seconds=duration_int if duration_int > 0 else None,
                        )
                    except AttributeError:
                        logger.debug("LogManager.update_session_state method not available, skipping log update")

            except Exception as e:
                logger.error(f"Failed to process Plivo hangup callback for session {session_id}: {e}", exc_info=True)
        else:
            logger.debug(f"Plivo hangup callback without session context: {data_dict}")

    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@plivo_router.post("/fallback", response_class=HTMLResponse)
async def fallback(request: Request):
    data = await request.form()
    logger.warning(f"Plivo Fallback Triggered: {data}")
    return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")


@plivo_router.post("/message", response_class=HTMLResponse)
async def message(request: Request):
    data = await request.form()
    logger.info(f"Plivo Message Received: {data}")
    # Acknowledge the message
    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


# --------Warm-Transfer Conference Endpoints--------
@plivo_router.post("/conference-xml", response_class=HTMLResponse)
@plivo_router.get("/conference-xml", response_class=HTMLResponse)
async def conference_xml(request: Request):
    """
    Returns XML to join a Plivo call to a conference room.
    Used to redirect the original caller to the conference during warm transfer.
    Supports both GET and POST methods.
    """
    timestamp = datetime.now().isoformat()
    room = request.query_params.get("room")

    if not room:
        logger.error(f"[{timestamp}] ⚠️ Conference XML requested but no room parameter provided")
        return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

    # Log which call is joining
    call_uuid = None
    if hasattr(request, 'form'):
        form = await request.form()
        call_uuid = form.get("CallUUID") or form.get("CallUUID")
    if not call_uuid:
        # Try query params
        call_uuid = request.query_params.get("CallUUID")

    logger.info(f"[{timestamp}] 🎤 CONFERENCE-XML ENDPOINT HIT")
    logger.info(f"   Call UUID joining conference: {call_uuid}")
    logger.info(f"   Conference room: {room}")
    logger.info(f"   Request method: {request.method}")

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Conference 
                        startConferenceOnEnter="true" 
                        endConferenceOnExit="false"
                        stayAlone="true">{room}</Conference>
                </Response>"""

    logger.info(f"[{timestamp}] 📋 CONFERENCE XML RETURNED (EXACT CONTENT):")
    return HTMLResponse(content=xml_content, media_type="application/xml")

@plivo_router.post("/conference-join", response_class=HTMLResponse)
@plivo_router.get("/conference-join", response_class=HTMLResponse)
async def plivo_conference_join(request: Request, background_tasks: BackgroundTasks, db: AsyncIOMotorDatabase = Depends(get_db_from_request)):
    """
    Called when supervisor answers.
    1. Stops hold music.
    2. Transfers the original caller into conference.
    3. Returns <Conference> XML for supervisor.
    
    Supports both GET and POST methods for compatibility with Plivo webhook configurations.
    """
    timestamp = datetime.now().isoformat()
    
    # Support both GET (query params) and POST (form data) methods
    if request.method == "GET":
        supervisor_call_uuid = request.query_params.get("CallUUID")
    else:
        form = await request.form()
        supervisor_call_uuid = form.get("CallUUID")
    
    session_id = request.query_params.get("session_id")
    tenant_id = request.query_params.get("tenant_id") or db.name

    logger.info(f"[{timestamp}] 🎯 /conference-join hit (method: {request.method})")
    logger.info(f"   Supervisor Call UUID: {supervisor_call_uuid}")
    logger.info(f"   Session ID: {session_id}")

    if not session_id:
        logger.error("❌ Missing session_id")
        return HTMLResponse("<Response><Hangup/></Response>", media_type="application/xml")

    try:
        client = plivo.RestClient(settings.PLIVO_AUTH_ID, settings.PLIVO_AUTH_TOKEN)
        session_manager = SessionManager(db)
        session = await session_manager.get_session(session_id)
        if not session:
            logger.error(f"❌ Session {session_id} not found")
            return HTMLResponse("<Response><Hangup/></Response>", media_type="application/xml")

        # # Get system phone number from session participants for credential lookup
        # system_phone_number = None
        # if session.participants:
        #     for participant in session.participants:
        #         if participant.role == ParticipantRole.SYSTEM and participant.phone_number:
        #             system_phone_number = participant.phone_number
        #             break
        
        # # Get credentials based on phone number (external or default)
        # auth_id, auth_token = await get_provider_credentials(
        #     phone_number=system_phone_number,
        #     provider="plivo",
        #     db=db
        # )
        # client = plivo.RestClient(auth_id, auth_token)

        # Get original call UUID from metadata first (stored during warm transfer)
        # Fall back to provider_session_id if not in metadata
        original_call_uuid = None
        if session.metadata:
            metadata = session.metadata if isinstance(session.metadata, dict) else session.metadata.__dict__ if hasattr(session.metadata, '__dict__') else {}
            original_call_uuid = metadata.get('original_call_uuid')
        
        # Fallback to provider_session_id if original_call_uuid not in metadata
        if not original_call_uuid:
            original_call_uuid = session.provider_session_id
            
        if not original_call_uuid:
            logger.error(f"❌ No original_call_uuid in metadata and no provider_session_id in session {session_id}")
            return HTMLResponse("<Response><Hangup/></Response>", media_type="application/xml")
        
        logger.info(f"[{timestamp}] 📞 Using original call UUID: {original_call_uuid}")

        conference_room = f"transfer_{session_id}"

        # Stop hold music on original caller
        try:
            client.calls.stop_playing(original_call_uuid)
            logger.info(f"[{timestamp}] ✅ Stopped hold music for call {original_call_uuid}")
            await asyncio.sleep(WARM_TRANSFER_HOLD_MUSIC_STOP_DELAY)
        except Exception as e:
            logger.warning(f"[{timestamp}] ⚠️ Could not stop hold music: {e}")
            
        base_url = request.base_url
        conference_xml_url = f"https://{base_url.hostname}/vagent/api/plivo/conference-xml?room={conference_room}"
        
        logger.info(f"[{timestamp}] 📋 Conference XML URL: {conference_xml_url}")

        # Transfer original caller into conference
        try:
            transfer_response = client.calls.update(
                call_uuid=original_call_uuid,
                legs="aleg",
                aleg_url=conference_xml_url,
                aleg_method="POST",
            )
            
            # Close the original caller's WebSocket now that we're transferring to conference
            # This is safe because the call is being transferred, not terminated
            try:
                original_websocket = plivo_websocket_manager.get_connection(session_id)
                if original_websocket:
                    await original_websocket.close()
                    plivo_websocket_manager.remove_connection(session_id)
                    logger.info(f"[{timestamp}] ✅ Closed original caller WebSocket after transfer initiated")
            except Exception as ws_err:
                logger.warning(f"[{timestamp}] ⚠️ Could not close original WebSocket: {ws_err}")
            
            background_tasks.add_task(cleanup_after_transfer, session_manager, session_id, tenant_id)
            logger.info(f"[{timestamp}] ✅ Transferred original caller {original_call_uuid} to {conference_room}")
            logger.info(f"[{timestamp}] Transfer response: {transfer_response}")
            
            await asyncio.sleep(WARM_TRANSFER_CONFERENCE_JOIN_DELAY)
            logger.info(f"[{timestamp}] ⏳ Waited for original caller to join conference")
        except Exception as e:
            logger.error(f"[{timestamp}] ❌ Conference join setup failed: {e}")

        # TEMPORARILY REMOVE Stream element to test if conference works
        # Once conference is working, we can add Stream back for transcription
        # Return XML for supervisor to join conference - SIMPLIFIED WITHOUT STREAM
        base_url = request.base_url
        # stream_url = f"wss://{base_url.hostname}/vagent/api/plivo/conference-voice/{tenant_id}/{session_id}"
    # <Stream bidirectional="false" keepCallAlive="false">{stream_url}</Stream>        
        # Return XML for supervisor to join conference WITH Stream element
        xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>Connecting you to the User.</Speak>

    <Conference startConferenceOnEnter="true" endConferenceOnExit="false" stayAlone="true">
        {conference_room}
    </Conference>
</Response>"""
        
        logger.info(f"[{timestamp}] ✅ Returning conference XML for supervisor")
        # logger.info(f"[{timestamp}] 📋 Stream URL: {stream_url}")
        return HTMLResponse(content=xml_response.strip(), media_type="application/xml")

    except Exception as e:
        logger.error(f"[{timestamp}] ❌ Transfer handler error: {e}", exc_info=True)
        return HTMLResponse("<Response><Hangup/></Response>", media_type="application/xml")
# -------------------------------------------------------------------------------------------------

async def cleanup_after_transfer(session_manager, session_id, tenant_id: str | None = None):
    """Background cleanup task after Plivo has begun transfer"""
    timestamp = datetime.now().isoformat()
    
    # Cancel any active warm transfer timeout since supervisor has joined
    try:
        from app.services.warm_transfer_service import cancel_warm_transfer_timeout, mark_warm_transfer_timeout_cancelled
        
        # Cancel local timeout task (if running on this pod)
        if cancel_warm_transfer_timeout(session_id):
            logger.info(f"[{timestamp}] ⏱️ Cancelled local warm transfer timeout - supervisor joined")
        
        # Also clear timeout state in database (for multi-pod environments)
        if tenant_id:
            await mark_warm_transfer_timeout_cancelled(session_id, tenant_id)
            logger.info(f"[{timestamp}] ⏱️ Cleared warm transfer timeout in database - supervisor joined")
    except Exception as timeout_err:
        logger.warning(f"[{timestamp}] ⚠️ Could not cancel warm transfer timeout: {timeout_err}")
    
    # CRITICAL: Immediately unmute transcription filter so normal conversation can resume
    # (Note: In warm transfer, the pipeline is typically closed after transfer, but just in case)
    try:
        from app.core.transports.base_transport_service import get_transcription_filter
        transcription_filter = get_transcription_filter(session_id)
        if transcription_filter:
            transcription_filter.set_warm_transfer_active(False)
            logger.info(f"[{timestamp}] 🔊 TranscriptionFilter unmuted after warm transfer")
    except Exception as tf_error:
        logger.debug(f"Could not unset TranscriptionFilter mute state: {tf_error}")
    
    # Clear warm_transfer_active flag since transfer is now complete
    try:
        await session_manager.update_session_fields(
            session_id,
            {
                "metadata.warm_transfer_active": False,
                "metadata.transfer_completed": True,
                "metadata.warm_transfer_timeout_at": None,
                "metadata.warm_transfer_original_call_uuid": None,
                "metadata.warm_transfer_supervisor_call_uuid": None,
            }
        )
        logger.info(f"[{timestamp}] ✅ Cleared warm_transfer_active flag for session {session_id}")
    except Exception as metadata_error:
        logger.warning(f"[{timestamp}] ⚠️ Could not update warm transfer metadata: {metadata_error}")