"""
RAG API Client

Handles query requests to the external RAG (knowledge base) API.
Uses the same pattern as CallbackSchedulerClient: session, tokens, and response handling.
"""

from typing import Any, Optional

import aiohttp
from loguru import logger
from pydantic import BaseModel

from app.core.config import settings


class RagQueryRequest(BaseModel):
    """Request payload for RAG query. Matches cbvista-ragbuilder QueryRequest."""

    query: str
    document_ids: Optional[list[str]] = None


class RagQueryResponse(BaseModel):
    """Response from RAG API - flexible to handle any response structure."""

    raw_response: dict[str, Any]
    status_code: int = 200

    @property
    def success(self) -> bool:
        """Check if response indicates success."""
        return self.status_code == 200

    def get_reply_text(self) -> str:
        """Extract reply/answer text from raw response."""
        data = self.raw_response
        return (
            data.get("reply")
            or data.get("answer")
            or data.get("response")
            or data.get("text")
            or ""
        )


class RagClient:
    """Client for interacting with the RAG (knowledge base) API."""

    def __init__(self, base_url: Optional[str] = None, timeout_secs: Optional[int] = None):
        self.base_url = (base_url or getattr(settings, "RAG_API_URL", None) or "").rstrip("/")
        self.timeout_secs = timeout_secs or 30

    async def query(
        self,
        session: aiohttp.ClientSession,
        query: str,
        document_ids: Optional[list[str]] = None,
        access_token: Optional[str] = None,
        id_token: Optional[str] = None,
    ) -> RagQueryResponse:
        """
        Query the RAG API and return the response.

        Args:
            session: HTTP client session to use
            query: The user's question to look up
            assistant_id: Assistant ID for scoping the knowledge base (required by API)
            document_ids: Optional list of document IDs to scope the search
            access_token: Optional access token for Authorization header
            id_token: Optional ID token (sent if provided)

        Returns:
            RagQueryResponse with raw_response and status_code

        Raises:
            ValueError: If RAG_API_URL is not configured
            aiohttp.ClientError: On network/API errors
        """
        if not self.base_url:
            raise ValueError("RAG API URL is not configured (RAG_API_URL)")

        # base_url is the full endpoint URL (e.g. https://.../rag/api/query)
        url = self.base_url
        payload = RagQueryRequest(
            query=query,
            document_ids=document_ids,
        ).model_dump(exclude_none=True)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if access_token:
            # API accepts raw JWT or Bearer; use raw token to match working curl
            headers["Authorization"] = access_token
        if id_token:
            headers["id_token"] = id_token

        logger.debug(f"RAG query to {url}, headers: {list(headers.keys())}")

        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout_secs),
        ) as response:
            try:
                response_data = await response.json() if "application/json" in (response.content_type or "") else {}
            except Exception:
                response_data = {}
            if response.status != 200:
                logger.warning(f"RAG API returned {response.status}: {response_data}")
            return RagQueryResponse(raw_response=response_data or {}, status_code=response.status)
