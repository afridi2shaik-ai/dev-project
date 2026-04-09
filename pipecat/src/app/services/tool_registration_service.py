"""Tool Registration Service

Provides a centralized, reusable service for registering custom tools
with any LLM service. This follows a plug-and-play architecture where
the same tool registration logic can be used across OpenAI, Gemini,
and any other LLM implementations.
"""

import functools
from typing import Any

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

# Legacy ToolManager removed - using BusinessToolManager for business tools
from app.schemas.services.agent import AgentConfig, ToolsConfig
from app.services.llm.utils import is_warm_transfer_enabled
from app.services.tool import register_business_tools_for_llm
from app.tools import hangup_call, warm_transfer, schedule_callback, rag_tool
from app.utils.field_type_utils import field_type_to_json_schema_type, normalize_field_type

logger.info("🔧 ToolRegistrationService module loaded successfully")


class ToolRegistrationService:
    """Centralized service for registering tools with LLM services.

    This service provides a plug-and-play architecture for tool registration
    that can be used across different LLM implementations (OpenAI, Gemini, etc.).
    """

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        # Legacy tool_manager removed - business tools handled by BusinessToolRegistrationService

    def _get_json_schema_type(self, field_type: Any) -> str:
        """Convert field type to valid JSON Schema type using unified utilities."""
        normalized_type = normalize_field_type(field_type)
        return field_type_to_json_schema_type(normalized_type)

    async def register_tools(self, llm_service, tools_config: ToolsConfig | None, agent_config: AgentConfig, aiohttp_session: aiohttp.ClientSession, available_tools: list | None = None, agent=None) -> list:
        """Register tools with an LLM service.

        Args:
            llm_service: The LLM service instance to register tools with
            tools_config: Configuration for tools to register
            agent_config: Agent configuration containing context
            aiohttp_session: HTTP session for API calls
            available_tools: List to append registered tools to

        Returns:
            List of registered tool functions
        """
        if available_tools is None:
            available_tools = []

        logger.info("🔧 Starting tool registration...")

        # Register standard tools
        await self._register_standard_tools(llm_service, available_tools, aiohttp_session, tools_config)

        # Register session context tool (ALWAYS AVAILABLE)
        await self._register_session_context_tool(llm_service, available_tools)

        # Register business tools (PRIMARY SYSTEM)
        if tools_config and tools_config.business_tools:
            logger.info(f"🔧 Registering {len(tools_config.business_tools)} business tools")
            await register_business_tools_for_llm(llm_service=llm_service, tools_config=tools_config, agent_config=agent_config, aiohttp_session=aiohttp_session, db=self.db, tenant_id=self.tenant_id, available_tools=available_tools, agent=agent)

        logger.info(f"🎯 Tool registration complete. Total tools: {len(available_tools)}")
        return available_tools

    async def _register_standard_tools(
        self,
        llm_service,
        available_tools: list,
        aiohttp_session: aiohttp.ClientSession,
        tools_config: ToolsConfig | None = None,
    ):
        """Register standard tools that are always available."""
        # Register hangup tool (check if enabled in config)
        hangup_enabled = True
        if tools_config and tools_config.hangup_tool:
            hangup_enabled = tools_config.hangup_tool.enabled

        if hangup_enabled:
            available_tools.append(hangup_call)

            # Register with LLM service if it supports direct function registration
            if hasattr(llm_service, "register_direct_function"):
                llm_service.register_direct_function(hangup_call)

            logger.info("✅ Registered hangup tool")
        else:
            logger.info("⏭️ Hangup tool disabled in configuration")

        # Register warm transfer tool (check if enabled in config)
        warm_transfer_enabled = is_warm_transfer_enabled(tools_config)

        if warm_transfer_enabled:
            available_tools.append(warm_transfer)

            if hasattr(llm_service, "register_direct_function"):
                llm_service.register_direct_function(warm_transfer)

            logger.info("✅ Registered warm transfer tool")
        else:
            logger.info("⏭️ Warm transfer tool disabled or missing required config")

        # Register call scheduler tool (check if enabled in config)
        # Only enable if explicitly configured and enabled in assistant config
        call_scheduler_enabled = False
        if tools_config and tools_config.call_scheduler_tool:
            call_scheduler_enabled = tools_config.call_scheduler_tool.enabled

        if call_scheduler_enabled:
            # Create a wrapper function that includes the aiohttp_session
            @functools.wraps(schedule_callback)
            async def schedule_callback_with_session(
                params,
                scheduled_at_utc: str,
                engaging_words: str,
                reason: str,
                phone_number: str,
            ):
                # Add the aiohttp_session to the params object
                params.aiohttp_session = aiohttp_session
                return await schedule_callback(params, scheduled_at_utc, engaging_words, reason, phone_number)

            available_tools.append(schedule_callback_with_session)

            if hasattr(llm_service, "register_direct_function"):
                llm_service.register_direct_function(schedule_callback_with_session)

            logger.info("✅ Registered call scheduler tool")
        else:
            logger.info("⏭️ Call scheduler tool disabled in configuration")

        # Register RAG tool (knowledge center)
        rag_tool_enabled = False
        if tools_config and tools_config.rag_tool:
            rag_tool_enabled = tools_config.rag_tool.enabled

        if rag_tool_enabled:
            @functools.wraps(rag_tool)
            async def rag_query_with_session(params, query: str, engaging_words: str = "", document_ids: list[str] | None = None):
                params.aiohttp_session = aiohttp_session
                return await rag_tool(params, query, engaging_words, document_ids=document_ids)

            available_tools.append(rag_query_with_session)
            if hasattr(llm_service, "register_direct_function"):
                llm_service.register_direct_function(rag_query_with_session)
            logger.info("✅ Registered RAG tool")
        else:
            logger.info("⏭️ RAG tool disabled in configuration")

    async def _register_session_context_tool(self, llm_service, available_tools: list):
        """Register the session context tool (always available)."""
        try:
            from app.tools.session_context_tool import get_session_info

            logger.info("🔧 Registering session context tool...")
            available_tools.append(get_session_info)

            if hasattr(llm_service, "register_direct_function"):
                llm_service.register_direct_function(get_session_info)

            logger.info("🎯 Registered session context tool")
        except Exception as e:
            logger.error(f"Failed to register session context tool: {e}")

    # NOTE: Legacy custom API tools and database tools have been replaced
    # by the unified business_tools system. All tool creation should now
    # use the BusinessTool schema and BusinessToolExecutor for consistency.


# Convenience function for easy integration
async def register_tools_for_llm(llm_service, tools_config: ToolsConfig | None, agent_config: AgentConfig, aiohttp_session: aiohttp.ClientSession, db: AsyncIOMotorDatabase | None = None, tenant_id: str | None = None, available_tools: list | None = None, agent=None) -> list:
    """Convenience function to register tools for an LLM service.

    Args:
        llm_service: The LLM service instance
        tools_config: Tools configuration
        agent_config: Agent configuration
        aiohttp_session: HTTP session for API calls
        db: Database connection (for database tools)
        tenant_id: Tenant identifier (for database tools)
        available_tools: List to append tools to

    Returns:
        List of registered tool functions
    """
    logger.info(f"🚀 register_tools_for_llm called with tools_config={bool(tools_config)}, db={db is not None}, tenant_id={tenant_id}")

    # Ensure database and tenant_id are provided as per architectural rule
    if db is None or not tenant_id:
        logger.warning("⚠️ Missing required database or tenant_id - skipping tool registration")
        return available_tools or []

    service = ToolRegistrationService(db=db, tenant_id=tenant_id)
    return await service.register_tools(llm_service=llm_service, tools_config=tools_config, agent_config=agent_config, aiohttp_session=aiohttp_session, available_tools=available_tools, agent=agent)
