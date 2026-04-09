from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional, Awaitable

import aiohttp
from loguru import logger
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.services.agent import AgentConfig
from app.utils.config_merge_utils import cleanup_discriminated_unions


class AssistantAPIError(Exception):
    pass


class AssistantAPINotFound(AssistantAPIError):
    pass


class AssistantAPIUnauthorized(AssistantAPIError):
    pass


class AssistantAPIClient:
    """Client to fetch assistant configuration from an external API.

    Sends both Authorization (Bearer) and id_token headers as required.
    Implements retries for 5xx responses.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        retry_attempts: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or settings.ASSISTANT_API_BASE_URL or "").rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.ASSISTANT_API_TIMEOUT
        self.retry_attempts = retry_attempts or settings.ASSISTANT_API_RETRY_ATTEMPTS
        if not self.base_url:
            logger.warning("ASSISTANT_API_BASE_URL is not configured. External assistant fetch will fail.")

    async def get_config(
        self,
        assistant_id: str,
        access_token: str,
        id_token: str,
        session: aiohttp.ClientSession,
        on_refresh_tokens: Optional[Callable[[], Awaitable[tuple[str, str]]]] = None,
        tenant_id: Optional[str] = None,
    ) -> AgentConfig:
        """Fetch assistant config and return AgentConfig.

        - Retries 5xx responses with exponential backoff.
        - On 401/403, if on_refresh_tokens provided, refresh once and retry.
        - Sends X-Tenant-ID header when tenant_id is provided, allowing the
          Assistant API to identify the tenant even if the JWT lacks the claim
          (e.g. service-account / M2M tokens).
        """
        if not assistant_id:
            raise ValueError("assistant_id is required")
        if not self.base_url:
            raise AssistantAPIError("Assistant API base URL is not configured")

        url = f"{self.base_url}/api/agentcall/assistants/{assistant_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "id_token": id_token,
            "Accept": "application/json",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        attempt = 0
        did_refresh = False
        backoff = 0.5

        while True:
            attempt += 1
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    status = resp.status
                    if status == 200:
                        data = await resp.json()
                        return self._parse_agent_config(data)
                    if status == 404:
                        raise AssistantAPINotFound(f"Assistant not found: {assistant_id}")
                    if status in (401, 403):
                        if not did_refresh and on_refresh_tokens is not None:
                            try:
                                did_refresh = True
                                logger.warning(f"Assistant API {status} for {assistant_id}. Refreshing tokens and retrying...")
                                new_access, new_id = await on_refresh_tokens()
                                headers["Authorization"] = f"Bearer {new_access}"
                                headers["id_token"] = new_id
                                continue
                            except Exception as e:  # pragma: no cover
                                logger.error(f"Token refresh failed: {e}")
                        if status == 401:
                            raise AssistantAPIUnauthorized("Unauthorized when calling Assistant API")
                        text = await resp.text()
                        raise AssistantAPIError(f"Assistant API error {status}: {text}")
                    if 500 <= status < 600 and attempt <= self.retry_attempts:
                        logger.warning(f"Assistant API {status}. Retrying attempt {attempt}/{self.retry_attempts}...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    # Other client errors
                    text = await resp.text()
                    raise AssistantAPIError(f"Assistant API error {status}: {text}")
            except asyncio.TimeoutError:
                if attempt <= self.retry_attempts:
                    logger.warning(f"Assistant API timeout. Retrying attempt {attempt}/{self.retry_attempts}...")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise AssistantAPIError("Assistant API request timed out")

    def _parse_agent_config(self, payload: dict[str, Any]) -> AgentConfig:
        """Parse and validate external response into AgentConfig.

        Expected shape: { tenant_id, assistant_id, config: <AgentConfig-like dict> }
        """
        try:
            config_data = payload.get("config")
            if not isinstance(config_data, dict):
                raise ValueError("'config' is missing or invalid in assistant API response")
            
            # Clean up invalid fields from discriminated unions before validation
            # This handles cases where external APIs return invalid field combinations
            config_data = cleanup_discriminated_unions(config_data.copy())
            
            # Construct AgentConfig directly; strict schema wrapper will be added in a separate task.
            agent_config = AgentConfig(**config_data)
            return agent_config
        except ValidationError as e:
            # Extract detailed validation error messages
            error_messages = []
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                error_type = error.get("type", "unknown")
                error_msg = error.get("msg", "Validation error")
                error_messages.append(f"{field_path}: {error_msg} (type: {error_type})")
            
            # Format all errors into a readable message
            formatted_errors = "\n".join(f"  - {msg}" for msg in error_messages)
            error_summary = f"Validation failed with {len(error_messages)} error(s):\n{formatted_errors}"
            
            # Log validation errors with full details
            logger.debug(f"agent config: {payload}")
            logger.error(f"Failed to parse AgentConfig from assistant API response - Validation errors:\n{error_summary}")
            logger.debug(f"Full validation error details: {e.errors()}")
            
            # Raise with detailed message
            raise AssistantAPIError(f"Invalid assistant configuration: {error_summary}")
        except Exception as e:
            logger.error(f"Failed to parse AgentConfig from assistant API response: {e}")
            raise AssistantAPIError(f"Invalid assistant configuration: {e}")
