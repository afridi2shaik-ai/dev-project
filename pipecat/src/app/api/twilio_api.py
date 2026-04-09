import json
import uuid

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry import trace
from starlette.responses import HTMLResponse
from twilio.rest import Client

from app import schemas
from app.agents import BaseAgent
from app.api.dependencies import get_current_user, get_db, get_db_from_request
from app.core import settings
from app.core.tracing_route import TracingAPIRoute
from app.core.transports.twilio_service import run_twilio_bot
from app.db.database import MongoClient, get_database
from app.managers.session_manager import SessionManager, DndBlockedError
from app.schemas.participant_schema import ParticipantDetails, ParticipantRole
from app.schemas.request_params import TwilioVoiceParams
from app.schemas.user_schema import UserInfo
from app.managers.phone_number_manager import PhoneNumberManager

tracer = trace.get_tracer(__name__)
twilio_router = APIRouter(route_class=TracingAPIRoute)


@twilio_router.post("/inbound", response_class=HTMLResponse)
async def inbound_call(request: Request, db: AsyncIOMotorDatabase = Depends(get_db_from_request)):
    with tracer.start_as_current_span("inbound_call_handler"):
        form = await request.form()
        call_sid = form.get("CallSid")

        # Capture full inbound request data for audit/diagnostics (parity with Plivo)
        inbound_call_details = dict(form)

        base_url = request.base_url
        session_id = request.query_params.get("session_id")
        tenant_id = db.name
        assistant_id = request.query_params.get("assistant_id") or "default"

        # Do not proceed without tenant_id
        if not tenant_id:
            logger.error("Missing tenant_id for inbound Twilio call")
            return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

        # Get the "To" number (system phone number) for credential lookup
        to_number = form.get("To")
        
        # Get credentials based on phone number (external or default) for inbound calls
        # This ensures any API operations later use the correct credentials
        phone_manager = PhoneNumberManager(db)
        account_sid, auth_token = await phone_manager.get_provider_credentials(
            phone_number=to_number,
            provider="twilio"
        )

        # If outbound call answer (session_id already known) → update session with provider_session_id and metadata
        if session_id:
            try:
                session_manager = SessionManager(db)
                await session_manager.update_session_fields(
                    session_id,
                    {
                        "provider_session_id": call_sid,
                        "metadata.inbound_http_request": inbound_call_details,
                        "metadata.provider_credentials": {"account_sid": account_sid, "provider": "twilio"}
                    },
                )
            except Exception as e:
                logger.error(f"Failed to update existing session for inbound Twilio call: {e}", exc_info=True)
        else:
            # New inbound call → create a session if tenant_id and assistant_id provided
            if not assistant_id:
                logger.error("Missing assistant_id for inbound Twilio call without session_id")
                return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

            session_manager = SessionManager(db)

            # Inbound semantics: USER called our SYSTEM number → put USER first for correct direction inference
            participants = [
                ParticipantDetails(role=ParticipantRole.USER, phone_number=form.get("From")),
                ParticipantDetails(role=ParticipantRole.SYSTEM, phone_number=to_number),
            ]

            # Create session
            session_id = str(uuid.uuid4())
            try:
                await session_manager.create_session(
                    session_id=session_id,
                    assistant_id=assistant_id,
                    participants=participants,
                    transport="twilio",
                    provider_session_id=call_sid,
                    # Explicitly set inbound direction to avoid participant-order ambiguity downstream
                    metadata={
                        "inbound_http_request": inbound_call_details, 
                        "call_direction": "inbound",
                        "provider_credentials": {"account_sid": account_sid, "provider": "twilio"}
                    },
                )
            except DndBlockedError as e:
                logger.warning(f"🚫 Inbound Twilio call blocked by DND for {e.identifier}: direction={e.direction}, policy={e.policy}")
                return HTMLResponse(content="<Response><Hangup/></Response>", media_type="application/xml")

        # Build Twilio Streams response
        wss_url = f"wss://{base_url.hostname}/vagent/api/twilio/voice/{call_sid}"

        async with aiofiles.open("src/app/templates/twilio_streams.xml") as f:
            xml_content = (
                (await f.read())
                .replace("{{WSS_URL}}", wss_url)
                .replace("{{SESSION_ID}}", session_id or "")
                .replace("{{TENANT_ID}}", tenant_id or "")
            )

        return HTMLResponse(content=xml_content, media_type="application/xml")


@twilio_router.websocket("/voice/{call_sid}")
async def voice(websocket: WebSocket, params: TwilioVoiceParams = Depends()):
    with tracer.start_as_current_span("twilio_websocket_handler"):
        await websocket.accept()
        try:
            start_data = websocket.iter_text()
            await start_data.__anext__()  # MediaFormat
            call_data_str = await start_data.__anext__()
            call_data = json.loads(call_data_str)  # Start

            # Log the entire start message from Twilio for debugging
            logger.info(f"Twilio Start Message: {call_data_str}")

            stream_sid = call_data["start"]["streamSid"]

            custom_params = call_data["start"].get("customParameters", {})
            session_id = custom_params.get("session_id")
            tenant_id = custom_params.get("tenant_id")
            if not session_id or not tenant_id:
                logger.error("session_id and tenant_id are required in customParameters")
                await websocket.close(code=1008)
                return

            client = MongoClient.get_client()
            if tenant_id not in await client.list_database_names():
                logger.warning(f"Attempted access to non-existent tenant database: {tenant_id}")
                await websocket.close(code=1008)
                return

            db = get_database(tenant_id, client)
            session_manager = SessionManager(db)
            agent_config = await session_manager.get_and_consume_config(session_id=session_id, transport_name="twilio", provider_session_id=params.call_sid)
            if not agent_config:
                logger.error(f"No session data or config found for session_id: {session_id}")
                await websocket.close()
                return

            logger.info(f"WebSocket connection accepted for stream: {stream_sid}, call: {params.call_sid}")
            agent = BaseAgent(agent_config=agent_config)
            await run_twilio_bot(websocket, stream_sid, params.call_sid, session_id, tenant_id, agent, call_data)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}")
            await websocket.close()


@twilio_router.post("/outbound-call", response_model=schemas.OutboundCallResponse)
async def outbound_call(request: Request, data: schemas.OutboundCallRequest, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    with tracer.start_as_current_span("outbound_call_handler"):
        base_url = request.base_url

        session_manager = SessionManager(db)
        assistant_id = data.assistant_id or "default"
        from_number = data.from_number or settings.TWILIO_PHONE_NUMBER

        # Get credentials based on phone number (external or default)
        phone_manager = PhoneNumberManager(db)
        account_sid, auth_token = await phone_manager.get_provider_credentials(
            phone_number=from_number,
            provider="twilio"
        )
        client = Client(account_sid, auth_token)

        # Create participant details
        participants = []
        participants.append(ParticipantDetails(role=ParticipantRole.SYSTEM, phone_number=from_number))

        user_name = None
        if data.assistant_overrides and data.assistant_overrides.customer_details:
            user_name = data.assistant_overrides.customer_details.name
        participants.append(ParticipantDetails(role=ParticipantRole.USER, phone_number=data.to, name=user_name))

        # Extract a clean dict of just the provided overrides
        overrides_dict = data.assistant_overrides.model_dump(exclude_unset=True) if data.assistant_overrides else None

        # Create user info for auditing
        user_info = UserInfo(id=current_user.get("sub"), name=current_user.get("name"), email=current_user.get("email"), role=current_user.get("role"))

        tenant_id = db.name
        session_id = str(uuid.uuid4())

        # Check for DND blocking before proceeding
        try:
            # Store call direction in metadata for proper direction detection
            metadata = {"call_direction": "outbound"}
            await session_manager.create_session(session_id=session_id, assistant_id=assistant_id, assistant_overrides=overrides_dict, participants=participants, created_by=user_info, transport="twilio", metadata=metadata)
        except DndBlockedError as e:
            logger.warning(f"🚫 Outbound Twilio call blocked by DND for {e.identifier}: direction={e.direction}, policy={e.policy}")
            detail = f"Call blocked by Do Not Disturb settings. Direction: {e.direction}, Policy: {e.policy.replace('_', ' ').title()}, Phone: {e.identifier}"
            raise HTTPException(status_code=403, detail=detail)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        answer_url = f"https://{base_url.hostname}/vagent/api/twilio/inbound?session_id={session_id}&tenant_id={tenant_id}"
        status_callback_url = f"https://{base_url.hostname}/vagent/api/twilio/status-callback?session_id={session_id}&tenant_id={tenant_id}"

        try:
            call = client.calls.create(
                from_=from_number,
                to=data.to,
                url=answer_url,
                method="POST",
                status_callback=status_callback_url,
                status_callback_method="POST",
                status_callback_event=["completed"],  # Receive callback when call ends
            )
            return {"message": "Call initiated", "call_id": call.sid, "session_id": session_id}
        except Exception as e:
            logger.error(f"Error making outbound call: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@twilio_router.post("/status-callback", response_class=HTMLResponse)
async def status_callback(request: Request):
    """
    Twilio status callback handler with enhanced session state management.

    Receives call status events from Twilio and updates session state based on call outcome.
    Maps Twilio CallStatus to appropriate SessionState values.

    Key Twilio Parameters:
    - CallSid: Unique call identifier
    - CallStatus: Call status (e.g., "no-answer", "busy", "failed", "completed")
    - CallDuration: Call duration in seconds
    - Direction: Call direction
    """
    with tracer.start_as_current_span("twilio_status_callback_handler"):
        data = await request.form()
        data_dict = dict(data)

        call_sid = data_dict.get("CallSid", "")
        call_status = data_dict.get("CallStatus", "")
        call_duration = data_dict.get("CallDuration", "0")
        direction = data_dict.get("Direction", "")

        logger.info(f"Twilio status callback: call_sid={call_sid}, call_status={call_status}, duration={call_duration}, direction={direction}")

        # Extract session info from query parameters
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
                    logger.warning(f"Session {session_id} not found for Twilio status callback.")
                    return HTMLResponse(content="<Response></Response>", media_type="application/xml")

                # Determine new session state based on call status
                import datetime

                from app.schemas.session_schema import SessionState

                new_state = current_session.state
                duration_seconds = None

                # Map Twilio CallStatus to session states
                if call_status == "no-answer":
                    new_state = SessionState.MISSED_CALL
                    logger.warning(f"Session {session_id}: Call not answered by user")
                elif call_status == "busy":
                    new_state = SessionState.BUSY
                    logger.info(f"Session {session_id}: User was busy")
                elif call_status == "failed":
                    new_state = SessionState.FAILED
                    logger.error(f"Session {session_id}: Call failed")
                elif call_status == "completed":
                    new_state = SessionState.COMPLETED
                    if call_duration and call_duration.isdigit():
                        duration_seconds = float(call_duration)
                    logger.info(f"Session {session_id}: Call completed (duration: {call_duration}s)")

                # Update session state if changed
                if new_state != current_session.state:
                    updates = {"state": new_state}

                    # Store call metadata in session.metadata.call_metadata for consistency
                    metadata = current_session.metadata or {}
                    metadata["call_metadata"] = {"provider": "twilio", "call_sid": call_sid, "call_status": call_status, "duration_seconds": duration_seconds, "direction": direction, "status_callback_timestamp": datetime.datetime.now(datetime.UTC).isoformat()}
                    updates["metadata"] = metadata

                    await session_manager.update_session_fields(session_id, updates)
                    logger.info(f"Twilio Call {call_sid} for session {session_id} updated to state: {new_state}")

                    # Update log session_state as well
                    from app.managers.log_manager import LogManager

                    log_manager = LogManager(db)
                    try:
                        await log_manager.update_session_state(session_id=session_id, new_state=new_state, duration_seconds=duration_seconds)
                    except AttributeError:
                        # Fallback if update_session_state method doesn't exist
                        logger.debug("LogManager.update_session_state method not available, skipping log update")

            except Exception as e:
                logger.error(f"Failed to process Twilio status callback for session {session_id}: {e}", exc_info=True)
        else:
            logger.debug(f"Twilio status callback without session context: {data_dict}")

    return HTMLResponse(content="<Response></Response>", media_type="application/xml")
