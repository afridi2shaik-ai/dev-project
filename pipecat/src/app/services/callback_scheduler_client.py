"""
Callback Scheduler Client

Handles scheduling callback requests with external scheduler APIs.
Currently configured to use dummy API endpoint, but designed to be easily
swappable to real scheduler services.
"""

import datetime
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger
from pydantic import BaseModel

from app.core import settings


class ScheduleCallbackRequest(BaseModel):
    """Request payload for scheduling a callback."""

    tenant_id: str
    session_id: str
    assistant_id: str
    requested_time_text: str  # Now contains the timestamp string
    scheduled_at_utc: str  # ISO format
    reason: str
    phone_number: str

    # Full context for scheduler
    user_details: Optional[Dict[str, Any]] = None
    transport_info: Optional[Dict[str, Any]] = None
    session_metadata: Optional[Dict[str, Any]] = None
    assistant_config: Optional[Dict[str, Any]] = None


class ScheduleCallbackResponse(BaseModel):
    """Response from scheduler API - flexible to handle any response structure."""

    raw_response: Dict[str, Any]  # Store the full raw response
    status_code: int = 200

    @property
    def success(self) -> bool:
        """Check if response indicates success."""
        return self.raw_response.get("success", self.status_code < 400)

    def get(self, key: str, default: Any = None) -> Any:
        """Get any field from raw response."""
        return self.raw_response.get(key, default)


class CallbackSchedulerClient:
    """Client for interacting with callback scheduler APIs."""

    def __init__(self, base_url: Optional[str] = None, timeout_secs: Optional[int] = None):
        self.base_url = base_url or settings.CALLBACK_SCHEDULER_BASE_URL
        self.timeout_secs = timeout_secs or settings.CALLBACK_SCHEDULER_TIMEOUT_SECS

    async def schedule_callback(
        self,
        request: ScheduleCallbackRequest,
        session: aiohttp.ClientSession,
        access_token: Optional[str] = None,
        id_token: Optional[str] = None,
    ) -> ScheduleCallbackResponse:
        """
        Schedule a callback by calling the scheduler API.

        Args:
            request: The callback scheduling request
            session: HTTP client session to use
            access_token: Optional access token for authentication
            id_token: Optional ID token for authentication

        Returns:
            Response from the scheduler API

        Raises:
            aiohttp.ClientError: On network/API errors
        """
        # Construct the full URL for the callback scheduling endpoint
        # TODO: When switching to the real API, verify the endpoint path matches your scheduler API:
        #   - Current path: "/callbacks/schedule" (works with dummy endpoint)
        #   - If your real API uses a different path (e.g., "/api/v1/schedule" or "/schedule"),
        #     update this line accordingly
        url = f"{self.base_url.rstrip('/')}/callback/schedule-callback"

        payload = request.model_dump()

        # Build headers with authentication tokens if provided
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if id_token:
            headers["x-id-token"] = id_token
            # Also support id_token header name for compatibility
            headers["id_token"] = id_token

        logger.info(f"📞 Scheduling callback via {url}")
        logger.debug(f"Payload: {payload}")
        logger.debug(f"Headers: {list(headers.keys())}")  # Log header names only, not values

        try:
            async with session.post(
                url,
                json=payload,
                headers=headers if headers else None,
                timeout=aiohttp.ClientTimeout(total=self.timeout_secs)
            ) as response:
                response.raise_for_status()
                response_data = await response.json()

                result = ScheduleCallbackResponse(
                    raw_response=response_data,
                    status_code=response.status
                )
                logger.info(f"✅ Callback scheduled successfully: {response_data}")

                return result

        except aiohttp.ClientError as e:
            logger.error(f"❌ Failed to schedule callback: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error scheduling callback: {e}")
            raise aiohttp.ClientError(f"Unexpected error: {e}")
