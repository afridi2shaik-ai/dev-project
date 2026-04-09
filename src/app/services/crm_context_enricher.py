"""CRM Context Enricher Service

Automatically enriches conversation context with CRM data on session start.
Uses existing BusinessToolExecutor to fetch data, then injects into context aggregator.
"""

import json
from typing import Any
import asyncio

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase
from pipecat.frames.frames import LLMMessagesAppendFrame

from app.schemas import SessionContext
from app.services.tool.business_tool_executor import BusinessToolExecutor
from app.services.tool.business_tool_service import BusinessToolService


async def enrich_context_from_crm(
    session_context: SessionContext,
    context_aggregator,
    tool_id: str,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
    agent=None,
) -> None:
    """
    Execute business tool async and add result to conversation context.

    This runs in the background on session start, automatically enriching
    the conversation with CRM data without requiring AI interaction.

    Args:
        session_context: Current session context with user/transport details
        context_aggregator: Context aggregator to inject results into
        tool_id: Business tool ID for CRM lookup
        db: Database connection
        tenant_id: Tenant identifier
        aiohttp_session: HTTP session for API calls
    """
    try:
        logger.info(f"🔍 Starting async CRM enrichment for session {session_context.session_id} with tool: {tool_id}")

        # 1. Load business tool config from database
        tool_service = BusinessToolService(db, tenant_id)
        tool_config = await tool_service.get_tool(tool_id)

        if not tool_config:
            logger.warning(f"CRM enrichment tool {tool_id} not found in database")
            return

        # 2. Auto-extract parameters from session context
        params = {}
        
        # Debug logging for session context
        logger.debug(f"🔍 Session context debug - user: {session_context.user}, transport: {session_context.transport}")
        if session_context.user:
            logger.debug(f"🔍 User details - name: {session_context.user.name}, email: {session_context.user.email}, user_id: {session_context.user.user_id}")
        if session_context.transport:
            logger.debug(f"🔍 Transport details - user_phone_number: {session_context.transport.user_phone_number}")
        
        if session_context.transport and session_context.transport.user_phone_number:
            params["phone"] = session_context.transport.user_phone_number
            logger.debug(f"Extracted phone from session: {params['phone']}")

        if session_context.user and session_context.user.email:
            params["email"] = session_context.user.email
            logger.debug(f"Extracted email from session: {params['email']}")

        if not params:
            logger.warning("No phone or email available in session context for CRM lookup")
            return

        # 3. Execute business tool (reuses existing executor!)
        executor = BusinessToolExecutor(db=db, tenant_id=tenant_id)
        result = await executor.execute_tool(
            tool_config=tool_config,
            business_parameters=params,
            engaging_words="",  # Silent - no TTS output
            aiohttp_session=aiohttp_session,
        )

        # 4. Inject results into context if successful
        logger.debug(f"🔍 Tool result: success={result.get('success')}, has_data={bool(result.get('data'))}, data_type={type(result.get('data'))}")
        
        if result.get("success") and result.get("data"):
            crm_data = result["data"]
            logger.debug(f"🔍 CRM data preview: {str(crm_data)[:200]}...")
            
            # Use the raw CRM data directly - no extraction needed
            await _inject_into_context(context_aggregator, crm_data)

            # Store enrichment data on agent for post-call actions
            if agent:
                agent._enrichment_data = crm_data
                agent._enrichment_success = True
                agent._customer_exists = True  # Customer found in CRM
                logger.debug("Stored CRM data on agent for post-call actions")

            logger.info(f"✅ CRM data successfully added to context for session {session_context.session_id}")
        else:
            # Log the full result for debugging
            logger.debug(f"🔍 Full result: {result}")
            error_msg = result.get("error", result.get("message", "Unknown error"))

            # Store enrichment failure on agent
            if agent:
                agent._enrichment_data = None
                agent._enrichment_success = False
                agent._customer_exists = False  # No customer found

            logger.warning(f"CRM enrichment failed: {error_msg}")

    except Exception as e:
        # Non-critical: Context enrichment failure shouldn't break the call
        logger.warning(f"CRM enrichment failed (non-critical): {e}")


async def _inject_into_context(context_aggregator, crm_data: dict[str, Any]) -> None:
    """
    Add CRM data as system message to conversation context using Pipecat's frame system.

    The AI will see this data and can reference it naturally in responses.
    This uses LLMMessagesAppendFrame which is the proper Pipecat way to add context.

    Args:
        context_aggregator: Context aggregator instance (OpenAIContextAggregatorPair)
        crm_data: CRM data dictionary to inject
    """
    # Format as readable context information
    content = _format_crm_data(crm_data)

    if content:
        # Create system message with CRM data
        system_message = {
            "role": "system",
            "content": content
        }

        # Use Pipecat's proper frame-based approach to add context
        # context_aggregator is a Pair, so we need to access the user aggregator
        # This is thread-safe and integrates properly with the pipeline
        # Retry briefly to avoid race with pipeline StartFrame in high-latency prod
        max_attempts = 5
        delay_seconds = 0.2
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                user_aggregator = context_aggregator.user()
                await user_aggregator.push_frame(
                    LLMMessagesAppendFrame([system_message])
                )
                logger.info("✅ Injected CRM context using LLMMessagesAppendFrame")
                logger.info(f"✅ CRM data successfully added to context: {content[:100]}...")
                last_error = None
                break
            except Exception as e:
                last_error = e
                # Common in prod: "StartFrame not received yet" — wait and retry
                if attempt < max_attempts:
                    await asyncio.sleep(delay_seconds)
                    delay_seconds *= 1.5
                else:
                    logger.warning(f"Failed to inject CRM context via frame after {max_attempts} attempts: {e}")


def _format_crm_data(crm_data: dict[str, Any]) -> str:
    """
    Format CRM data into a readable string for system context.
    
    Performs a complete data dump of all CRM information using JSON serialization
    for optimal performance with large datasets. No recursive formatting overhead.

    Args:
        crm_data: Dictionary of CRM data fields (can be nested)

    Returns:
        Formatted string with complete CRM information dump, or empty string if no data
    """
    if not crm_data:
        return ""
    
    try:
        # Use JSON dump for fast, complete data serialization
        # indent=2 makes it readable while being performant
        json_dump = json.dumps(crm_data, indent=2, ensure_ascii=False, default=str)
        
        return f"CUSTOMER INFORMATION FROM CRM (Complete Data Dump):\n{json_dump}"
    except Exception as e:
        logger.warning(f"Failed to serialize CRM data: {e}")
        # Fallback to string representation if JSON serialization fails
        return f"CUSTOMER INFORMATION FROM CRM (Raw Data):\n{str(crm_data)}"
