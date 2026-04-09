"""Dummy API router for testing custom tool functionality.

This router provides simple test endpoints that can be used to verify
that custom tools are working correctly with various parameter combinations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter()


class DummyResponse(BaseModel):
    """Standard response format for dummy API endpoints."""

    success: bool = True
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    endpoint: str
    method: str
    query_params: dict[str, Any] | None = None
    body_data: dict[str, Any] | None = None
    headers_received: dict[str, str] | None = None
    message: str


class CreateUserRequest(BaseModel):
    """Request body for creating a user."""

    name: str = Field(..., description="Full name of the user")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="User role")
    department: str | None = Field(None, description="Department name")
    salary: int | None = Field(None, description="Annual salary")


@router.get("/simple")
async def simple_get():
    """Simple GET endpoint with no parameters.
    Perfect for testing tools with no required parameters.
    """
    return DummyResponse(endpoint="/dummy/simple", method="GET", message="Simple GET request successful - no parameters required!")


@router.get("/query-required")
async def query_required(tenant_id: str = Query(..., description="Tenant identifier"), version: str = Query(..., description="API version"), notify: bool | None = Query(None, description="Whether to send notifications")):
    """GET endpoint with required query parameters.
    Tests tools that require specific query parameters.
    """
    query_params = {"tenant_id": tenant_id, "version": version, "notify": notify}

    return DummyResponse(endpoint="/dummy/query-required", method="GET", query_params=query_params, message=f"Query parameters received successfully! Tenant: {tenant_id}, Version: {version}")


@router.post("/body-required")
async def body_required(user_data: CreateUserRequest):
    """POST endpoint with required body fields.
    Tests tools that require structured request bodies.
    """
    return DummyResponse(endpoint="/dummy/body-required", method="POST", body_data=user_data.dict(), message=f"User '{user_data.name}' created successfully with role '{user_data.role}'")


@router.post("/query-and-body")
async def query_and_body(user_data: CreateUserRequest, tenant_id: str = Query(..., description="Tenant identifier"), version: str = Query(..., description="API version"), notify: bool | None = Query(None, description="Whether to send notifications")):
    """POST endpoint with BOTH required query parameters AND required body fields.
    This is the comprehensive test for complex API scenarios.
    """
    query_params = {"tenant_id": tenant_id, "version": version, "notify": notify}

    return DummyResponse(endpoint="/dummy/query-and-body", method="POST", query_params=query_params, body_data=user_data.dict(), message=f"User '{user_data.name}' created in tenant '{tenant_id}' using API version '{version}'")


@router.get("/with-auth")
async def with_auth(user_id: str = Query(..., description="User ID to fetch"), include_details: bool | None = Query(False, description="Include detailed information")):
    """GET endpoint that expects authentication headers.
    Tests tools with authentication configurations.
    """
    return DummyResponse(endpoint="/dummy/with-auth", method="GET", query_params={"user_id": user_id, "include_details": include_details}, message=f"User {user_id} data retrieved successfully (details: {include_details})")


@router.post("/echo")
async def echo_request(request_data: dict[str, Any]):
    """POST endpoint that echoes back whatever data is sent.
    Useful for testing various data types and structures.
    """
    return DummyResponse(endpoint="/dummy/echo", method="POST", body_data=request_data, message="Echo successful - data received and returned")


@router.get("/slow")
async def slow_endpoint(delay: int | None = Query(2, description="Delay in seconds")):
    """Slow endpoint for testing timeout configurations."""
    import asyncio

    await asyncio.sleep(delay)

    return DummyResponse(endpoint="/dummy/slow", method="GET", query_params={"delay": delay}, message=f"Slow endpoint completed after {delay} seconds")


@router.post("/error")
async def error_endpoint(error_code: int | None = Query(400, description="HTTP error code to return")):
    """Endpoint that returns errors for testing error handling."""
    error_messages = {400: "Bad Request - Invalid parameters", 401: "Unauthorized - Authentication required", 403: "Forbidden - Access denied", 404: "Not Found - Resource not found", 500: "Internal Server Error - Something went wrong"}

    message = error_messages.get(error_code, "Unknown error")
    raise HTTPException(status_code=error_code, detail=message)


@router.get("/types-test")
async def types_test(string_param: str = Query(..., description="String parameter"), number_param: int = Query(..., description="Number parameter"), boolean_param: bool = Query(..., description="Boolean parameter"), optional_param: str | None = Query(None, description="Optional parameter")):
    """Endpoint for testing different parameter types.
    Tests the JSON Schema type mapping fixes.
    """
    return DummyResponse(endpoint="/dummy/types-test", method="GET", query_params={"string_param": string_param, "number_param": number_param, "boolean_param": boolean_param, "optional_param": optional_param}, message=f"Type test successful: string='{string_param}', number={number_param}, boolean={boolean_param}")


@router.get("/crm/lookup")
async def crm_lookup(phone: str | None = Query(None, description="Customer phone number"), email: str | None = Query(None, description="Customer email")):
    """Simple CRM lookup endpoint for testing auto-enrichment.

    Returns mock customer data based on phone or email.
    Perfect for testing the session context enrichment feature.
    """
    if not phone and not email:
        raise HTTPException(status_code=400, detail="Either phone or email is required")

    # Mock customer data
    customer_data = {"name": "John Smith", "status": "premium", "account_since": "2020-01-15", "company": "Acme Corp", "phone": phone or "+1-555-1234", "email": email or "john@example.com", "customer_id": "CUST-12345"}

    return {"success": True, "data": customer_data, "message": f"Customer found: {customer_data['name']}"}


@router.post("/crm/interactions")
async def crm_create_interaction(request: Request):
    """Create new interaction/activity record in CRM (POST).

    This simulates logging a completed call as a new interaction record.
    Perfect for testing post-call CREATE_INTERACTION actions.
    """
    try:
        body = await request.json()

        # Generate interaction ID
        session_id = body.get("session_id", "unknown")
        interaction_id = f"INT-{hash(session_id) % 100000}"

        # Log received data
        logger.info(f"📝 Creating CRM interaction: {interaction_id}")
        logger.debug(f"Interaction data: {body}")

        return {
            "success": True,
            "interaction_id": interaction_id,
            "message": f"Call interaction logged: {body.get('outcome', 'Unknown')} ({body.get('call_duration', 0)}s)",
            "data": {"interaction_id": interaction_id, "phone": body.get("phone"), "email": body.get("email"), "contact_name": body.get("contact_name"), "summary": body.get("summary"), "outcome": body.get("outcome"), "duration_seconds": body.get("call_duration"), "created_at": "2025-10-24T13:00:00Z"},
        }
    except Exception as e:
        logger.error(f"Error creating CRM interaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/crm/contacts/{customer_id}")
async def crm_update_contact(customer_id: str, request: Request):
    """Update existing contact with call data (PATCH).

    This simulates updating an existing customer record with latest call information.
    Perfect for testing post-call UPDATE_CONTACT actions.
    """
    try:
        body = await request.json()

        # Log received data
        logger.info(f"📝 Updating CRM contact: {customer_id}")
        logger.debug(f"Update data: {body}")

        return {"success": True, "customer_id": customer_id, "message": "Contact updated successfully with latest call data", "data": {"customer_id": customer_id, "last_contact_date": body.get("call_ended_at"), "last_interaction_summary": body.get("summary"), "status": body.get("outcome"), "notes": body.get("call_notes"), "updated_at": "2025-10-24T13:00:00Z"}}
    except Exception as e:
        logger.error(f"Error updating CRM contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crm/leads")
async def crm_create_lead(request: Request):
    """Create new lead in CRM (POST).

    This simulates creating a new lead for customers not found in pre-call lookup.
    Perfect for testing post-call CREATE_LEAD actions with ON_CUSTOMER_NEW condition.
    """
    try:
        body = await request.json()
        # Generate lead ID
        phone = body.get("phone", "unknown")
        lead_id = f"LEAD-{hash(phone) % 100000}"
        # Log received data
        logger.info(f"📝 Creating CRM lead: {lead_id}")
        logger.debug(f"Lead data: {body}")
        return {"success": True, "lead_id": lead_id, "message": "New lead created from call", "data": {"lead_id": lead_id, "phone": body.get("phone"), "email": body.get("email"), "contact_name": body.get("contact_name"), "source": "inbound_call", "summary": body.get("summary"), "outcome": body.get("outcome"), "status": "new", "created_at": "2025-10-24T13:00:00Z"}}
    except Exception as e:
        logger.error(f"Error creating CRM lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Global storage for scheduled callbacks (for development visibility)
_scheduled_callbacks: list[dict] = []


@router.post("/callbacks/schedule")
async def schedule_callback(request: Request):
    """Schedule a callback for later execution.

    This is a dummy endpoint that simulates scheduling a callback.
    In production, this would be replaced with a real scheduler service.

    Expects a payload with full context for callback scheduling.

    TODO: When ready to use the real callback scheduler API:
      1. Update CALLBACK_SCHEDULER_BASE_URL in config.py (or via env var)
      2. Verify the real API endpoint path matches "/callbacks/schedule" in callback_scheduler_client.py
      3. Ensure the real API accepts the same payload structure (ScheduleCallbackRequest)
      4. This dummy endpoint can be removed once the real API is integrated
    """
    try:
        body = await request.json()
        logger.debug(f"Callback request body: {body}")
        logger.debug(f"Callback Headers: {request.headers}")

        # Generate a job ID
        import uuid
        job_id = f"CB-{str(uuid.uuid4())[:8].upper()}"

        # Extract key information
        scheduled_at_utc = body.get("scheduled_at_utc")
        phone_number = body.get("phone_number")
        tenant_id = body.get("tenant_id")
        session_id = body.get("session_id")

        # Store the callback for dev visibility
        callback_record = {
            "job_id": job_id,
            "scheduled_at_utc": scheduled_at_utc,
            "phone_number": phone_number,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "requested_time_text": body.get("requested_time_text"),
            "reason": body.get("reason"),
            "created_at": datetime.now().isoformat(),
            "status": "scheduled",
            "payload_preview": {k: v for k, v in body.items() if k not in ["assistant_config", "session_metadata"]}
        }
        _scheduled_callbacks.append(callback_record)

        # Log the scheduling
        logger.info(f"📞 Dummy callback scheduled: {job_id} for {phone_number} at {scheduled_at_utc}")
        logger.debug(f"Callback record: {callback_record}")
        return {
            "success": True,
            "job_id": job_id,
            "scheduled_at_utc": scheduled_at_utc,
            "message": f"Callback scheduled successfully for {scheduled_at_utc}",
            "received_payload_preview": callback_record["payload_preview"]
        }

    except Exception as e:
        logger.error(f"Error scheduling callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callbacks")
async def list_scheduled_callbacks():
    """List all scheduled callbacks (for development/testing)."""
    return {
        "success": True,
        "callbacks": _scheduled_callbacks,
        "total": len(_scheduled_callbacks)
    }


@router.delete("/callbacks/{job_id}")
async def cancel_callback(job_id: str):
    """Cancel a scheduled callback (for development/testing)."""
    global _scheduled_callbacks

    for i, callback in enumerate(_scheduled_callbacks):
        if callback["job_id"] == job_id:
            callback["status"] = "cancelled"
            logger.info(f"📞 Callback {job_id} cancelled")
            return {
                "success": True,
                "job_id": job_id,
                "message": "Callback cancelled successfully"
            }

    raise HTTPException(status_code=404, detail=f"Callback {job_id} not found")