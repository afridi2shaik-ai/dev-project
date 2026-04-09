"""
Business Tool Registration Service

This service registers business tools with the LLM, creating simple function interfaces
that hide API complexity from the AI. Each business tool becomes a clean function
that the AI can call with business parameters.
"""

from typing import Any

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pipecat.adapters.schemas.function_schema import FunctionSchema

from app.schemas.core.business_tool_schema import BusinessParameter, BusinessTool
from app.schemas.services.agent import AgentConfig, ToolsConfig
from app.services.tool.business_tool_service import BusinessToolService
from app.utils.field_type_utils import create_json_schema_property
from app.utils.function_call_utils import extract_function_parameters, log_function_call


class BusinessToolRegistrationService:
    """Service for registering business tools with LLM services."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str, agent=None):
        self.db = db
        self.tenant_id = tenant_id
        self.business_tool_service = BusinessToolService(db, tenant_id, agent=agent)

    async def register_business_tools(self, llm_service, tools_config: ToolsConfig | None, agent_config: AgentConfig, aiohttp_session: aiohttp.ClientSession, available_tools: list | None = None) -> list:
        """Register business tools with the LLM service."""

        if not tools_config or not tools_config.business_tools:
            logger.debug("No business tools to register")
            return available_tools or []

        logger.info(f"Registering {len(tools_config.business_tools)} business tools")

        # Get enabled tool IDs
        enabled_tool_ids = [tool_ref.tool_id for tool_ref in tools_config.business_tools if tool_ref.enabled]

        if not enabled_tool_ids:
            logger.info("No enabled business tools found")
            return available_tools or []

        # Load business tools from database
        business_tools = await self.business_tool_service.get_tools_by_ids(enabled_tool_ids)

        # Store registered tools for tracking (separate from available_tools)
        registered_tools = []

        for tool_id, business_tool in business_tools.items():
            try:
                # Create function schema for the business tool
                self._create_function_schema(business_tool)

                # Create the actual function implementation
                tool_function = self._create_business_tool_function(business_tool, aiohttp_session)

                # Add to available tools list and register directly with LLM service
                available_tools.append(tool_function)
                llm_service.register_direct_function(tool_function)

                registered_tools.append({"name": business_tool.name, "type": "business_tool", "tool_id": tool_id, "description": business_tool.description})

                logger.info(f"✅ Registered business tool: {business_tool.name}")

            except Exception as e:
                logger.error(f"❌ Failed to register business tool {business_tool.name}: {e}")

        logger.info(f"Successfully registered {len(business_tools)} business tools")
        # Don't return anything - available_tools list is modified in place

    def _create_function_schema(self, business_tool: BusinessTool) -> FunctionSchema:
        """Create a Pipecat FunctionSchema for a business tool."""

        # Build properties for business parameters
        properties = {}
        required_params = []

        for param in business_tool.parameters:
            # Convert business parameter to JSON schema property
            param_schema = self._business_parameter_to_json_schema(param)
            properties[param.name] = param_schema

            if param.required:
                required_params.append(param.name)

        # Note: We don't add engaging_words to the schema anymore
        # The tool's configured engaging_words will be used automatically

        return FunctionSchema(name=business_tool.name, description=business_tool.description, properties=properties, required=required_params)

    def _business_parameter_to_json_schema(self, param: BusinessParameter) -> dict[str, Any]:
        """Convert a business parameter to JSON schema format using unified utilities."""
        return create_json_schema_property(param.type, param.description, param.examples)

    def _create_business_tool_function(self, business_tool: BusinessTool, aiohttp_session: aiohttp.ClientSession):
        """Create the actual function that will be called by the LLM."""

        async def business_tool_function(params, **kwargs):
            """
            Business tool function that executes the configured API call.

            This function:
            1. Extracts business parameters from kwargs
            2. Calls the BusinessToolService to execute the tool
            3. Returns the result to the LLM
            """

            try:
                # Extract parameters using standardized utility
                business_parameters, metadata_parameters = extract_function_parameters(kwargs)

                # Log the function call
                log_function_call(business_tool.name, business_parameters, metadata_parameters)

                # Use configured engaging words from the tool (not from LLM)
                # This ensures we use the tool's configured engaging words, not "Processing your request..."
                engaging_words = business_tool.engaging_words if business_tool.engaging_words and business_tool.engaging_words.strip() else "Processing your request..."

                logger.debug(f"Using configured engaging words: '{engaging_words}'")

                # Execute the business tool
                # Engaging words will be spoken INSIDE the executor after validation passes
                result = await self.business_tool_service.execute_tool(
                    tool_id=business_tool.tool_id,
                    business_parameters=business_parameters,
                    engaging_words=engaging_words,
                    aiohttp_session=aiohttp_session,
                    result_callback=params.result_callback,
                    params=params  # Pass params so executor can speak engaging words after validation
                )

                return result

            except Exception as e:
                logger.error(f"Error in business tool function {business_tool.name}: {e}")

                error_result = {"success": False, "error": f"Business tool execution failed: {e!s}", "error_type": type(e).__name__, "tool_name": business_tool.name, "tool_id": business_tool.tool_id}

                # Always call result callback
                await params.result_callback(error_result)
                return error_result

        # Set function metadata
        business_tool_function.__name__ = business_tool.name
        business_tool_function.__doc__ = business_tool.description

        return business_tool_function


async def register_business_tools_for_llm(llm_service, tools_config: ToolsConfig | None, agent_config: AgentConfig, aiohttp_session: aiohttp.ClientSession, db: AsyncIOMotorDatabase, tenant_id: str, available_tools: list | None = None, agent=None):
    """
    Register business tools for an LLM service.

    This is the main entry point for registering business tools.
    It creates a BusinessToolRegistrationService and delegates to it.
    The available_tools list is modified in place.
    """

    service = BusinessToolRegistrationService(db, tenant_id, agent=agent)

    await service.register_business_tools(llm_service=llm_service, tools_config=tools_config, agent_config=agent_config, aiohttp_session=aiohttp_session, available_tools=available_tools)
