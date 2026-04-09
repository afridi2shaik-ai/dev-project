"""
Business Tool Service

This service handles the execution of business tools and provides infrastructure layer
functionality. CRUD operations are handled by BusinessToolManager in the managers layer
following the Domain-Driven Design architecture.
"""

import hashlib
import time
from typing import Any

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.managers.business_tool_manager import BusinessToolManager
from app.schemas.core.business_tool_schema import (
    BusinessTool,
    BusinessToolCreateRequest,
    BusinessToolListItem,
    BusinessToolTestRequest,
    BusinessToolTestResponse,
    BusinessToolUpdateRequest,
)
from app.schemas.user_schema import UserInfo
from app.services.tool.business_tool_executor import BusinessToolExecutor


class BusinessToolService:
    """Service for executing business tools. CRUD operations delegated to BusinessToolManager."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str, agent=None):
        self.db = db
        self.tenant_id = tenant_id
        self.agent = agent  # Store agent reference for cache access
        self.manager = BusinessToolManager(db, tenant_id)
        self.executor = BusinessToolExecutor(db=db, tenant_id=tenant_id, agent=agent)

    def set_agent(self, agent):
        """Set the agent reference after service initialization.

        This allows the executor to access the session-scoped pre-request cache.

        Args:
            agent: BaseAgent instance
        """
        self.agent = agent
        self.executor.agent = agent
        logger.debug("BusinessToolService: Agent reference set for pre-request caching")

    async def create_tool(self, tool_data: BusinessToolCreateRequest, user_info: UserInfo) -> str:
        """Create a new business tool."""
        return await self.manager.create_tool(tool_data, user_info)

    async def get_tool(self, tool_id: str) -> BusinessTool | None:
        """Get a business tool by ID."""
        return await self.manager.get_tool(tool_id)

    async def get_tools_by_ids(self, tool_ids: list[str]) -> dict[str, BusinessTool]:
        """Get multiple business tools by their IDs."""
        return await self.manager.get_tools_by_ids(tool_ids)

    async def update_tool(self, tool_id: str, update_data: BusinessToolUpdateRequest, user_info: UserInfo) -> bool:
        """Update an existing business tool."""
        return await self.manager.update_tool(tool_id, update_data, user_info)

    async def delete_tool(self, tool_id: str, user_info: UserInfo) -> bool:
        """Delete a business tool."""
        return await self.manager.delete_tool(tool_id, user_info)

    async def list_tools(self, skip: int = 0, limit: int = 20) -> tuple[list[BusinessToolListItem], int]:
        """List business tools with pagination."""
        return await self.manager.list_tools(skip, limit)

    async def execute_tool(self, tool_id: str, business_parameters: dict[str, Any], engaging_words: str, aiohttp_session: aiohttp.ClientSession, result_callback: callable, params=None) -> dict[str, Any]:
        """Execute a business tool with the given parameters."""
        logger.info(f"Executing business tool: {tool_id}")

        try:
            # Load tool configuration
            tool_config = await self.get_tool(tool_id)
            if not tool_config:
                raise ValueError(f"Tool {tool_id} not found")

            # Execute the tool
            result = await self.executor.execute_tool(
                tool_config=tool_config,
                business_parameters=business_parameters,
                engaging_words=engaging_words,
                aiohttp_session=aiohttp_session,
                params=params  # Pass params for speaking engaging words after validation
            )

            # Call result callback
            await result_callback(result)

            logger.info(f"Successfully executed business tool: {tool_id}")
            return result

        except Exception as e:
            logger.error(f"Error executing business tool {tool_id}: {e}")

            error_result = {"success": False, "error": f"Tool execution failed: {e!s}", "error_type": type(e).__name__, "tool_id": tool_id, "timestamp": time.time()}

            # Always call result callback, even for errors
            await result_callback(error_result)
            return error_result

    async def test_tool(self, tool_id: str, test_request: BusinessToolTestRequest, aiohttp_session: aiohttp.ClientSession) -> BusinessToolTestResponse:
        """Test a business tool with the given parameters."""
        logger.info(f"Testing business tool: {tool_id}")

        start_time = time.perf_counter()

        try:
            # Load tool configuration
            tool_config = await self.get_tool(tool_id)
            if not tool_config:
                return BusinessToolTestResponse(success=False, error_message=f"Tool {tool_id} not found")

            # Execute the tool
            result = await self.executor.execute_tool(tool_config=tool_config, business_parameters=test_request.parameters, engaging_words=test_request.engaging_words or "Testing...", aiohttp_session=aiohttp_session)

            execution_time = (time.perf_counter() - start_time) * 1000

            return BusinessToolTestResponse(success=result.get("success", True), status_code=result.get("status_code"), response_data=result.get("raw_response"), processed_response=result, execution_time_ms=execution_time, transformation_log=result.get("transformation_log", []))

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000

            logger.error(f"Error testing business tool {tool_id}: {e}")

            return BusinessToolTestResponse(success=False, error_message=str(e), execution_time_ms=execution_time)

    async def validate_tool_ids(self, tool_ids: list[str]) -> tuple[list[str], list[str]]:
        """Validate that tool IDs exist and return valid/invalid lists."""
        return await self.manager.validate_tool_ids(tool_ids)

    async def get_tool_categories(self) -> list[str]:
        """Get all unique tool categories for this tenant."""
        return await self.manager.get_tool_categories()

    def _create_cache_key(self, tool_id: str, parameters: dict[str, Any]) -> str:
        """Create a cache key for tool execution results."""
        param_str = str(sorted(parameters.items()))
        cache_input = f"{tool_id}:{param_str}"
        return hashlib.sha256(cache_input.encode()).hexdigest()[:16]
