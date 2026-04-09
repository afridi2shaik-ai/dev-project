"""CRM MCP (Model Context Protocol) integration for Pipecat LLM services.

Uses Pipecat's MCPClient (pipecat-ai[mcp]) with streamable HTTP or SSE transports.
Requires a spec-compliant MCP server; plain JSON-RPC POST handlers are not supported.

CRM MCP is enabled when ``tools.crm.enabled`` and ``CRM_MCP_URL`` is set (API base;
``/mcp/stream`` is appended unless the URL already ends with ``/stream``).

MCP Authorization uses the same TokenProvider + tenant_id path as the RAG tool when
``tenant_id`` is available. Falls back to ``bearer_token`` on the wire config if
TokenProvider fails or ``tenant_id`` is missing. Explicit ``Authorization`` in
``headers`` always wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from loguru import logger
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from app.core.config import settings
from app.schemas.services.tools import ToolsConfig

try:
    from mcp.client.session_group import SseServerParameters, StreamableHttpParameters
    from pipecat.services.mcp_service import MCPClient
except ModuleNotFoundError:  # pragma: no cover - optional extra
    SseServerParameters = None  # type: ignore[misc, assignment]
    StreamableHttpParameters = None  # type: ignore[misc, assignment]
    MCPClient = None  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class _McpWireConfig:
    """Resolved connection parameters for MCPClient (internal)."""

    url: str
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    headers: dict[str, str] = field(default_factory=dict)
    bearer_token: str | None = None
    terminate_on_close: bool = True
    http_timeout_seconds: float = 30.0
    sse_read_timeout_seconds: float = 300.0


def mcp_integration_available() -> bool:
    return MCPClient is not None and StreamableHttpParameters is not None


def _resolved_crm_mcp_stream_url() -> str:
    """Build streamable MCP URL from ``CRM_MCP_URL`` (API base through ``/crm-api``).

    Example: ``https://host/crm-api`` → ``https://host/crm-api/mcp/stream``.
    If the value already ends with ``/stream``, it is used as-is (full URL override).
    """
    base = (settings.CRM_MCP_URL or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/stream"):
        return base
    return f"{base}/mcp/stream"


def _effective_mcp_wire_config(tools_config: ToolsConfig | None) -> _McpWireConfig | None:
    """Resolve wire config from ``tools.crm`` + ``CRM_MCP_URL``."""
    if not tools_config:
        return None
    crm = tools_config.crm
    if crm and crm.enabled:
        url = _resolved_crm_mcp_stream_url()
        if url:
            return _McpWireConfig(url=url)
        logger.warning("tools.crm.enabled but CRM_MCP_URL is empty; skipping CRM MCP")
    return None


def mcp_tools_enabled(tools_config: ToolsConfig | None) -> bool:
    return _effective_mcp_wire_config(tools_config) is not None


def _headers_include_authorization(headers: dict[str, str]) -> bool:
    return any(k.lower() == "authorization" for k in headers)


async def resolve_mcp_auth_headers(cfg: _McpWireConfig, tenant_id: str | None) -> dict[str, str]:
    """Build HTTP headers for MCP, including Authorization (same source as RAG when possible).

    Precedence:
    1. Existing ``Authorization`` in ``cfg.headers`` — unchanged.
    2. If ``tenant_id`` is set — ``TokenProvider.get_tokens_for_tenant`` → ``Bearer <access_token>``.
    3. Else ``cfg.bearer_token`` → ``Bearer <token>``.
    4. Else no Authorization (logged).
    """
    headers = dict(cfg.headers or {})

    if _headers_include_authorization(headers):
        logger.info(
            "MCP auth: using existing Authorization from MCP headers | tenant_id={} | url={}",
            tenant_id,
            (cfg.url or "").strip()[:80],
        )
        return headers

    used_token_provider = False
    if tenant_id:
        try:
            from app.services.token_provider import TokenProvider

            access_token, _id_token = await TokenProvider.get_tokens_for_tenant(tenant_id)
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
                used_token_provider = True
                preview = access_token[-8:] if len(access_token) > 8 else "****"
                logger.info(
                    "MCP auth: TokenProvider access token for tenant_id={} (Authorization: Bearer …{}) | same path as RAG tool",
                    tenant_id,
                    preview,
                )
            else:
                logger.warning("MCP auth: TokenProvider returned empty access_token for tenant_id={}", tenant_id)
        except Exception as exc:
            logger.warning(
                "MCP auth: TokenProvider failed for tenant_id={}: {} — trying bearer_token from MCP config",
                tenant_id,
                exc,
            )

    if not used_token_provider:
        bt = (cfg.bearer_token or "").strip()
        if bt:
            headers["Authorization"] = f"Bearer {bt}"
            logger.info(
                "MCP auth: using bearer_token from MCP config | tenant_id={}",
                tenant_id,
            )
        else:
            logger.warning(
                "MCP auth: no Authorization (tenant_id={!r}, TokenProvider unused or failed, bearer_token empty)",
                tenant_id,
            )

    return headers


def build_mcp_server_params_with_headers(cfg: _McpWireConfig, headers: dict[str, str]) -> Any:
    """Build SseServerParameters or StreamableHttpParameters using pre-resolved headers."""
    if not mcp_integration_available():
        raise RuntimeError("MCP dependencies missing; install pipecat-ai[mcp].")

    hdr: dict[str, str] | None = headers if headers else None
    url = cfg.url.strip()
    logger.debug(
        "MCP params: transport={} url={} header_keys={}",
        cfg.transport,
        url[:120],
        list((hdr or {}).keys()),
    )

    if cfg.transport == "sse":
        return SseServerParameters(
            url=url,
            headers=hdr,
            timeout=cfg.http_timeout_seconds,
            sse_read_timeout=cfg.sse_read_timeout_seconds,
        )

    return StreamableHttpParameters(
        url=url,
        headers=hdr,
        timeout=timedelta(seconds=cfg.http_timeout_seconds),
        sse_read_timeout=timedelta(seconds=cfg.sse_read_timeout_seconds),
        terminate_on_close=cfg.terminate_on_close,
    )


async def build_mcp_server_params_async(tools_config: ToolsConfig, tenant_id: str | None) -> Any:
    """Resolve auth (TokenProvider / bearer / headers) then build streamable HTTP or SSE params."""
    cfg = _effective_mcp_wire_config(tools_config)
    assert cfg is not None
    headers = await resolve_mcp_auth_headers(cfg, tenant_id)
    return build_mcp_server_params_with_headers(cfg, headers)


async def merge_openai_pipeline_tools_with_mcp(
    llm,
    tools_config: ToolsConfig | None,
    available_tools: list | None,
    tenant_id: str | None = None,
) -> list:
    """Append MCP tool schemas to direct-function tools; register MCP handlers on ``llm``."""
    base = list(available_tools or [])
    if not mcp_tools_enabled(tools_config):
        return base
    if not mcp_integration_available():
        logger.warning("MCP is enabled in tools config but pipecat-ai[mcp] is not available; skipping MCP tools.")
        return base

    assert tools_config is not None
    cfg = _effective_mcp_wire_config(tools_config)
    assert cfg is not None
    logger.info(
        "MCP OpenAI pipeline: starting tool registration | tenant_id={} | transport={} | url_preview={}",
        tenant_id,
        cfg.transport,
        (cfg.url or "").strip()[:100],
    )

    try:
        params = await build_mcp_server_params_async(tools_config, tenant_id)
        mcp = MCPClient(server_params=params)
        mcp_schema = await mcp.register_tools(llm)
        n = len(mcp_schema.standard_tools) if mcp_schema and mcp_schema.standard_tools else 0
        logger.info("MCP OpenAI pipeline: registered {} MCP tool(s) on LLM", n)
        return base + list(mcp_schema.standard_tools)
    except Exception:
        logger.exception("MCP tool registration failed for OpenAI pipeline; continuing without MCP tools.")
        return base


async def get_mcp_tools_schema_only(
    tools_config: ToolsConfig | None,
    tenant_id: str | None = None,
) -> ToolsSchema | None:
    """Fetch MCP tool schemas without binding to an LLM (for Gemini-style construction)."""
    if not mcp_tools_enabled(tools_config):
        return None
    if not mcp_integration_available():
        logger.warning("MCP is enabled in tools config but pipecat-ai[mcp] is not available; skipping MCP tools.")
        return None

    assert tools_config is not None
    eff = _effective_mcp_wire_config(tools_config)
    logger.info(
        "MCP Gemini path: fetching tools schema only | tenant_id={} | url_preview={}",
        tenant_id,
        (eff.url or "").strip()[:100] if eff else None,
    )

    try:
        params = await build_mcp_server_params_async(tools_config, tenant_id)
        mcp = MCPClient(server_params=params)
        schema = await mcp.get_tools_schema()
        n = len(schema.standard_tools) if schema and schema.standard_tools else 0
        logger.info("MCP Gemini path: fetched {} MCP tool schema(s)", n)
        return schema
    except Exception:
        logger.exception("MCP get_tools_schema failed; continuing without MCP tools.")
        return None


async def bind_mcp_tools_schema_to_llm(
    llm,
    tools_config: ToolsConfig | None,
    mcp_schema: ToolsSchema | None,
    tenant_id: str | None = None,
) -> None:
    """Register MCP tool handlers on a constructed LLM (Gemini / two-step flow)."""
    if mcp_schema is None or not mcp_tools_enabled(tools_config):
        return
    if not mcp_integration_available():
        return

    assert tools_config is not None
    logger.info("MCP Gemini path: binding MCP tool schema to LLM | tenant_id={}", tenant_id)

    try:
        params = await build_mcp_server_params_async(tools_config, tenant_id)
        mcp = MCPClient(server_params=params)
        await mcp.register_tools_schema(mcp_schema, llm)
        logger.info("MCP Gemini path: register_tools_schema completed")
    except Exception:
        logger.exception("MCP register_tools_schema failed for Gemini pipeline.")
