"""Agent Mapping from AgentConfig Schema

Provides a simple function to fetch a human agent's phone number
from the warm transfer tool configuration.
"""

from typing import Optional

from loguru import logger

from app.schemas.services.tools import ToolsConfig


async def get_agent_phone_number(
    session_id: str,
    agent_id: str | None = None,
    agent_name: str | None = None,
    tenant_id: str | None = None,
    tools_config: ToolsConfig | None = None,
) -> Optional[str]:
    """
    Resolve the phone number for an agent based on tool configuration.

    Warm transfer currently supports a single configured phone number that
    represents the target supervisor/agent. If more advanced routing is needed,
    the tool config should be extended accordingly (matching the reference SDK).
    """

    logger.info(
        f"[Session {session_id}] Resolving agent "
        f"id={agent_id}, name={agent_name}, tenant={tenant_id}"
    )

    if tools_config and tools_config.Warm_transfer_tool:
        cfg = tools_config.Warm_transfer_tool
        if cfg.enabled and cfg.phone_number:
            logger.info(
                f"[Session {session_id}] Using phone number from WarmTransferConfig: {cfg.phone_number}"
            )
            return cfg.phone_number

    logger.warning(
        f"[Session {session_id}] No agent phone number configured for warm transfer tool."
    )
    return None