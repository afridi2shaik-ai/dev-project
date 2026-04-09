import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, InputParams
from pipecat.services.google.llm import GoogleLLMService

from app.core import settings
from app.schemas.services.agent import AgentConfig, ToolsConfig
from app.services.llm.utils import (
    is_hangup_enabled,
    is_warm_transfer_enabled,
)
from app.services.crm_mcp import bind_mcp_tools_schema_to_llm, get_mcp_tools_schema_only
from app.services.tool_registration_service import register_tools_for_llm


async def create_gemini_multimodal_llm_service(
    messages: list[dict[str, str]] | None = None,
    model: str = "gemini-2.0-flash-live-001",
    voice_id: str = "Prik",
    temperature: float = 0.7,
    system_prompt: str | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools_config: ToolsConfig | None = None,
    agent_config: AgentConfig | None = None,
    aiohttp_session: aiohttp.ClientSession | None = None,
    db: AsyncIOMotorDatabase | None = None,
    tenant_id: str | None = None,
    agent=None,
):
    # Use the ToolRegistrationService
    available_tools = []

    logger.info(f"🔧 Gemini Multimodal LLM Service: tools_config exists: {bool(tools_config)}")
    if tools_config and agent_config and aiohttp_session:
        available_tools = await register_tools_for_llm(
            llm_service=None,  # Gemini doesn't need direct registration
            tools_config=tools_config,
            agent_config=agent_config,
            aiohttp_session=aiohttp_session,
            db=db,
            tenant_id=tenant_id,
            available_tools=available_tools,
            agent=agent,
        )
    else:
        from app.tools import hangup_call, warm_transfer

        if is_hangup_enabled(tools_config):
            available_tools.append(hangup_call)
        else:
            logger.info("Hangup tool disabled via config; skipping Gemini multimodal fallback registration.")

        if is_warm_transfer_enabled(tools_config):
            available_tools.append(warm_transfer)
        else:
            logger.info("Warm transfer tool disabled or unconfigured; skipping Gemini multimodal fallback registration.")

    mcp_schema = await get_mcp_tools_schema_only(tools_config, tenant_id=tenant_id)
    mcp_tool_schemas = list(mcp_schema.standard_tools) if mcp_schema else []
    tools = ToolsSchema(standard_tools=list(available_tools) + mcp_tool_schemas)
    llm = GeminiLiveLLMService(api_key=settings.GEMINI_API_KEY, voice_id=voice_id, model=model, system_instruction=system_prompt, tools=tools, temperature=temperature, top_p=top_p, max_output_tokens=max_tokens, input_params=InputParams(include_conversation_turn_start_frames=True, include_conversation_turn_end_frames=True))

    await bind_mcp_tools_schema_to_llm(llm, tools_config, mcp_schema, tenant_id=tenant_id)

    context_aggregator = OpenAILLMContext(messages if messages else [])
    context_aggregator.set_messages(messages if messages else [])
    context_aggregator.set_completion_callback(llm.process_text_completion)

    return llm, context_aggregator, messages if messages else []


async def create_google_text_llm_service(
    messages: list[dict[str, str]] | None = None,
    model: str = "gemini-pro",
    temperature: float = 0.7,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools_config: ToolsConfig | None = None,
    agent_config: AgentConfig | None = None,
    aiohttp_session: aiohttp.ClientSession | None = None,
    db: AsyncIOMotorDatabase | None = None,
    tenant_id: str | None = None,
    agent=None,
):
    # Use the ToolRegistrationService
    available_tools = []

    logger.info(f"🔧 Google Text LLM Service: tools_config exists: {bool(tools_config)}")
    if tools_config and agent_config and aiohttp_session:
        available_tools = await register_tools_for_llm(
            llm_service=None,  # Gemini doesn't need direct registration
            tools_config=tools_config,
            agent_config=agent_config,
            aiohttp_session=aiohttp_session,
            db=db,
            tenant_id=tenant_id,
            available_tools=available_tools,
            agent=agent,
        )
    else:
        from app.tools import hangup_call, warm_transfer

        if is_hangup_enabled(tools_config):
            available_tools.append(hangup_call)
        else:
            logger.info("Hangup tool disabled via config; skipping Gemini text fallback registration.")

        if is_warm_transfer_enabled(tools_config):
            available_tools.append(warm_transfer)
        else:
            logger.info("Warm transfer tool disabled or unconfigured; skipping Gemini text fallback registration.")

    mcp_schema = await get_mcp_tools_schema_only(tools_config, tenant_id=tenant_id)
    mcp_tool_schemas = list(mcp_schema.standard_tools) if mcp_schema else []
    tools = ToolsSchema(standard_tools=list(available_tools) + mcp_tool_schemas)
    llm = GoogleLLMService(
        api_key=settings.GEMINI_API_KEY,
        model=model,
        tools=tools,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    await bind_mcp_tools_schema_to_llm(llm, tools_config, mcp_schema, tenant_id=tenant_id)

    context_aggregator = OpenAILLMContext(messages if messages else [])
    context_aggregator.set_messages(messages if messages else [])
    context_aggregator.set_completion_callback(llm.process_text_completion)

    return llm, context_aggregator, messages if messages else []
