import asyncio
import datetime

import aiohttp
from loguru import logger

from app.core.config import settings
from app.services.token_provider import TokenProvider


# All event types we send; other microservice compares these strings.
# Add new events here when you add new emit_event call sites.
EVENTS = [
    "session_start",
    "session_end",
    "session_artifacts_ready",
]


def _is_emitter_enabled() -> bool:
    enabled = getattr(settings, "EVENTMANAGER_ENABLED", False)
    if enabled is True:
        return True
    return False


class EventEmitter:
    def __init__(self):
        self.api_url = (getattr(settings, "EVENTMANAGER_API_URL") or "").rstrip("/")
        self.enabled = _is_emitter_enabled()

    async def emit_event(
        self,
        event_type: str,
        data: dict,
        tenant_id: str | None = None,
    ) -> None:
        
        if not self.enabled:
            return
        if not self.api_url:
            logger.warning("Event manager enabled but EVENTMANAGER_API_URL is not set, skipping emit")
            return
        if event_type not in EVENTS:
            logger.warning("Unknown event type {} not in EVENTS, not sending", event_type)
            return

        payload = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id

        headers = {}
        if tenant_id:
            try:
                _, id_token = await TokenProvider.get_tokens_for_tenant(tenant_id)
                if id_token:
                    headers["id_token"] = id_token
            except Exception as e:
                logger.debug("Event manager: no id_token for tenant {}: {}", tenant_id, e)

        url = f"{self.api_url}/core/events"
        session_id_in_data = (data.get("session_id") or data.get("_id")) if isinstance(data, dict) else None
        logger.info(
            "Event manager: event_type={} | session_id={} | tenant_id={}",
            event_type,
            session_id_in_data,
            tenant_id,
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        response_text = await resp.text()
                        logger.warning(
                            "Event manager: request failed | event_type={} | status={} | response={}",
                            event_type,
                            resp.status,
                            response_text[:300] if response_text else "(empty)",
                        )
                    else:
                        logger.info("Event manager: event_type={} sent ok", event_type)
        except asyncio.TimeoutError:
            logger.warning("Event manager: event_type={} timed out", event_type)
        except Exception as e:
            logger.warning("Event manager: event_type={} failed | error={}", event_type, e)
