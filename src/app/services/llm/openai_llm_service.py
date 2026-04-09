import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.openai.llm import OpenAILLMService

from app.core import settings
from app.schemas.services.agent import AgentConfig, ToolsConfig
from app.services.llm.utils import is_hangup_enabled, is_warm_transfer_enabled
from app.services.crm_mcp import merge_openai_pipeline_tools_with_mcp
from app.tools.hangup_tool import hangup_call
from app.tools.warm_transfer_tool import warm_transfer


async def check_litellm_service_availability(aiohttp_session: aiohttp.ClientSession) -> bool:
    """Check if the Litellm service is available."""
    try:
        async with aiohttp_session.get(settings.LITELLM_BASE_URL + "/health/liveliness") as response:
            if response.status == 200:
                return True
    except aiohttp.ClientError as e:
        logger.error(f"Litellm service unavailable: {e}")
    return False

async def create_llm_service_with_context(
    messages: list[dict[str, str]] | None = None,
    model: str | None = "gpt-4o",
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    tools_config: ToolsConfig | None = None,
    agent_config: AgentConfig | None = None,
    aiohttp_session: aiohttp.ClientSession | None = None,
    db: AsyncIOMotorDatabase | None = None,
    tenant_id: str | None = None,
    agent=None,
):
    if await check_litellm_service_availability(aiohttp_session):
        logger.info("Litellm service is available, using Litellm.")
        llm = OpenAILLMService(
            api_key=settings.LITELLM_API_KEY,
            base_url=settings.LITELLM_BASE_URL,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
        )
    else:
        logger.warning("Litellm service is unavailable, falling back to the respective model.")
        llm = OpenAILLMService(
            api_key=settings.OPENAI_API_KEY,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
        )
    context = OpenAILLMContext(messages)

    # Register tools based on configuration
    available_tools = []

    logger.info(f"🔧 OpenAI LLM Service: tools_config exists: {bool(tools_config)}")
    if tools_config and agent_config and aiohttp_session:
        # Use the ToolRegistrationService
        from app.services.tool_registration_service import register_tools_for_llm

        available_tools = await register_tools_for_llm(llm_service=llm, tools_config=tools_config, agent_config=agent_config, aiohttp_session=aiohttp_session, db=db, tenant_id=tenant_id, available_tools=available_tools, agent=agent)
    else:
        if is_hangup_enabled(tools_config):
            available_tools.append(hangup_call)
            llm.register_direct_function(hangup_call)
        else:
            logger.info("Hangup tool disabled via config; skipping fallback registration.")

        if is_warm_transfer_enabled(tools_config):
            available_tools.append(warm_transfer)
            llm.register_direct_function(warm_transfer)
        else:
            logger.info("Warm transfer tool disabled or unconfigured; skipping fallback registration.")

    available_tools = await merge_openai_pipeline_tools_with_mcp(
        llm, tools_config, available_tools, tenant_id=tenant_id
    )

    # Advertise all available tools to the model
    if available_tools:
        context.set_tools(ToolsSchema(standard_tools=available_tools))
    context_aggregator = llm.create_context_aggregator(context)

    return llm, context_aggregator, messages
