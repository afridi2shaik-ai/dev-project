"""Helper functions for determining tool availability for LLM services."""

from __future__ import annotations

from app.schemas.services.tools import ToolsConfig


def is_hangup_enabled(tools_config: ToolsConfig | None) -> bool:
    """Return True if the hangup tool should be available."""

    if not tools_config or tools_config.hangup_tool is None:
        return True
    return bool(tools_config.hangup_tool.enabled)


def is_warm_transfer_enabled(tools_config: ToolsConfig | None) -> bool:
    """Return True if the warm transfer tool should be available."""

    if not tools_config or tools_config.Warm_transfer_tool is None:
        return False

    cfg = tools_config.Warm_transfer_tool
    return bool(cfg.enabled and cfg.phone_number)

