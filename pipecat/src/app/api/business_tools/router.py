"""
Business Tools API Router

Provides REST endpoints for managing business tools.
These tools are business-focused and hide API complexity from the AI.
"""

import math
from typing import Any

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import PaginationParams, get_current_user, get_db, get_http_client
from app.managers.business_tool_manager import BusinessToolManager
from app.schemas.core.business_tool_schema import (
    BusinessTool,
    BusinessToolCreateRequest,
    BusinessToolListItem,
    BusinessToolTestRequest,
    BusinessToolTestResponse,
    BusinessToolUpdateRequest,
    FieldType,
)
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.user_schema import UserInfo
from app.services.tool.business_tool_service import BusinessToolService

business_tools_router = APIRouter()


def create_user_info_from_token(current_user: dict) -> UserInfo:
    """Create a UserInfo object from the current user token."""
    return UserInfo(id=current_user.get("sub", ""), name=current_user.get("name"), email=current_user.get("email"), role=current_user.get("role"))


@business_tools_router.post("", response_model=str, status_code=201)
async def create_business_tool(tool_data: BusinessToolCreateRequest, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Create a new business tool."""
    manager = BusinessToolManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    try:
        tool_id = await manager.create_tool(tool_data, user_info)
        logger.info(f"Created business tool {tool_id}: {tool_data.name}")
        return tool_id
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating business tool: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@business_tools_router.get("", response_model=PaginatedResponse[BusinessToolListItem])
async def list_business_tools(db: AsyncIOMotorDatabase = Depends(get_db), pagination: PaginationParams = Depends(), current_user: dict = Depends(get_current_user)):
    """List business tools with pagination and optional filtering."""
    manager = BusinessToolManager(db, db.name)

    tools, total_items = await manager.list_tools(skip=pagination.skip, limit=pagination.limit)

    total_pages = math.ceil(total_items / pagination.limit) if pagination.limit > 0 else 0

    return PaginatedResponse(total_items=total_items, total_pages=total_pages, current_page=pagination.page, data=tools)


@business_tools_router.get("/field-types", response_model=dict[str, Any])
async def get_field_types():
    """Get available field types for business parameters."""
    return {"field_types": [{"value": field_type.value, "label": field_type.value.title(), "description": _get_field_type_description(field_type)} for field_type in FieldType]}


@business_tools_router.get("/{tool_id}", response_model=BusinessTool)
async def get_business_tool(tool_id: str, db: AsyncIOMotorDatabase = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get a business tool by ID."""
    manager = BusinessToolManager(db, db.name)
    tool = await manager.get_tool(tool_id)

    if not tool:
        raise HTTPException(status_code=404, detail="Business tool not found")

    return tool


@business_tools_router.put("/{tool_id}", response_model=BusinessTool)
async def update_business_tool(tool_id: str, update_data: BusinessToolUpdateRequest, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Update an existing business tool."""
    manager = BusinessToolManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    success = await manager.update_tool(tool_id, update_data, user_info)
    if not success:
        raise HTTPException(status_code=404, detail="Business tool not found")

    # Return updated tool
    updated_tool = await manager.get_tool(tool_id)
    return updated_tool


@business_tools_router.delete("/{tool_id}", status_code=204)
async def delete_business_tool(tool_id: str, current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Delete a business tool."""
    manager = BusinessToolManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    success = await manager.delete_tool(tool_id, user_info)
    if not success:
        raise HTTPException(status_code=404, detail="Business tool not found")


@business_tools_router.post("/validate-ids")
async def validate_business_tool_ids(tool_ids: list[str], db: AsyncIOMotorDatabase = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Validate that business tool IDs exist and are accessible."""
    manager = BusinessToolManager(db, db.name)

    valid_ids, invalid_ids = await manager.validate_tool_ids(tool_ids)

    return {"valid_ids": valid_ids, "invalid_ids": invalid_ids, "total_requested": len(tool_ids), "total_valid": len(valid_ids), "total_invalid": len(invalid_ids)}


@business_tools_router.post("/{tool_id}/test", response_model=BusinessToolTestResponse)
async def test_business_tool(tool_id: str, test_request: BusinessToolTestRequest, db: AsyncIOMotorDatabase = Depends(get_db), aiohttp_session: aiohttp.ClientSession = Depends(get_http_client), current_user: dict = Depends(get_current_user)):
    """Test a business tool with the provided parameters."""
    service = BusinessToolService(db, db.name)

    try:
        result = await service.test_tool(tool_id, test_request, aiohttp_session)
        return result
    except Exception as e:
        logger.error(f"Error testing business tool {tool_id}: {e}")
        return BusinessToolTestResponse(success=False, error_message=f"Test failed: {e!s}")


def _get_field_type_description(field_type: FieldType) -> str:
    """Get description for a field type."""
    descriptions = {
        FieldType.STRING: "Text input (any string value)",
        FieldType.INTEGER: "Whole numbers (e.g., 1, 42, -10)",
        FieldType.BOOLEAN: "True/false values",
        FieldType.ARRAY: "List of values (comma-separated)",
        FieldType.EMAIL: "Email address format",
        FieldType.PHONE_NUMBER: "Phone number in international format",
        FieldType.URL: "Web URL (http/https)",
        FieldType.DATE: "Date in YYYY-MM-DD format",
        FieldType.DATETIME: "Date and time in ISO format",
    }
    return descriptions.get(field_type, "Unknown field type")
