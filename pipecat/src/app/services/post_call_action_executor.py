"""
Post-call CRM action executor.

Executes configured CRM actions after call completion:
- CREATE_INTERACTION: Log call as new interaction/activity record
- UPDATE_CONTACT: Update existing contact with call outcome
- CREATE_LEAD: Create new lead if customer doesn't exist
- UPDATE_DEAL: Update sales opportunity/deal

Actions are executed based on:
- Priority (ascending order)
- Execution conditions (always, on_customer_exists, etc.)
- Sequential or parallel execution mode
- Retry mechanism with LLM-based parameter fixing
"""

import asyncio
from typing import Any

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.constants import (
    DEFAULT_POST_CALL_RETRY_DELAY_SECONDS,
    DEFAULT_POST_CALL_RETRY_LLM_MODEL,
    DEFAULT_POST_CALL_RETRY_LLM_TEMPERATURE,
    DEFAULT_POST_CALL_RETRY_MAX_ATTEMPTS,
    EXPONENTIAL_BACKOFF_MULTIPLIER,
)
from app.schemas import Session
from app.schemas.core.call_lifecycle_schema import (
    ActionExecutionCondition,
    CallLifecycleConfig,
    CRMActionType,
    PostCallAction,
    PostCallRetryConfig,
)
from app.services.post_call_parameter_fixer import fix_parameters_with_llm
from app.services.tool.business_tool_executor import BusinessToolExecutor
from app.services.tool.business_tool_service import BusinessToolService


async def execute_post_call_actions(
    session: Session,
    call_summary: dict[str, Any] | None,
    call_lifecycle_config: CallLifecycleConfig,
    enrichment_data: dict[str, Any] | None,
    customer_exists: bool,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
) -> dict[str, Any]:
    """
    Execute all configured post-call CRM actions.

    Args:
        session: Session object with call data
        call_summary: AI-generated call summary (if summarization enabled)
        call_lifecycle_config: Call lifecycle configuration
        enrichment_data: Data retrieved from pre-call enrichment (None if no enrichment or failed)
        customer_exists: Whether customer was found in pre-call enrichment
        db: Database connection
        tenant_id: Tenant identifier
        aiohttp_session: HTTP session for API calls

    Returns:
        Dictionary with execution results for each action
    """
    try:
        logger.info(f"💾 Starting post-call actions for session {session.session_id}")

        # Check if post-call actions are enabled
        if not call_lifecycle_config.post_call_enabled:
            logger.debug("Post-call actions disabled in configuration")
            return {"status": "disabled", "actions": []}

        # Check if we have any actions to execute
        if not call_lifecycle_config.post_call_actions:
            logger.debug("No post-call actions configured")
            return {"status": "no_actions", "actions": []}

        # Check enrichment requirement
        enrichment_success = enrichment_data is not None
        if call_lifecycle_config.require_enrichment_for_post_actions and not enrichment_success:
            logger.warning(
                "Post-call actions skipped: require_enrichment_for_post_actions=true "
                "but enrichment was not successful"
            )
            return {"status": "enrichment_required", "actions": []}

        # Determine call completion status (for now, assume success if we reached post-call)
        call_completed_successfully = session.state != "abandoned"

        # Filter and sort actions
        enabled_actions = [action for action in call_lifecycle_config.post_call_actions if action.enabled]

        if not enabled_actions:
            logger.debug("All post-call actions are disabled")
            return {"status": "all_disabled", "actions": []}

        # Filter actions by execution condition
        actions_to_execute = []
        for action in enabled_actions:
            should_execute = _should_execute_action(
                action=action,
                customer_exists=customer_exists,
                call_completed_successfully=call_completed_successfully,
                enrichment_success=enrichment_success,
                require_enrichment=call_lifecycle_config.require_enrichment_for_post_actions,
            )

            if should_execute:
                actions_to_execute.append(action)
            else:
                logger.debug(
                    f"Skipping action {action.action_type} (tool: {action.tool_id}) - "
                    f"condition not met (execution_condition={action.execution_condition}, "
                    f"customer_exists={customer_exists})"
                )

        if not actions_to_execute:
            logger.info("No post-call actions meet execution conditions")
            return {"status": "no_actions_match_conditions", "actions": []}

        # Sort by priority
        actions_to_execute.sort(key=lambda x: x.priority)

        logger.info(f"Executing {len(actions_to_execute)} post-call action(s)")

        # Find CREATE_LEAD tool ID for fallback (if configured)
        create_lead_tool_id = None
        for action in call_lifecycle_config.post_call_actions:
            if action.action_type == CRMActionType.CREATE_LEAD and action.enabled:
                create_lead_tool_id = action.tool_id
                break

        # Execute actions
        if call_lifecycle_config.parallel_execution:
            # Parallel execution
            results = await _execute_actions_parallel(
                actions=actions_to_execute,
                session=session,
                call_summary=call_summary,
                enrichment_data=enrichment_data,
                db=db,
                tenant_id=tenant_id,
                aiohttp_session=aiohttp_session,
                fallback_create_lead_tool_id=create_lead_tool_id,
                default_retry_config=call_lifecycle_config.default_retry_config,
            )
        else:
            # Sequential execution
            results = await _execute_actions_sequential(
                actions=actions_to_execute,
                session=session,
                call_summary=call_summary,
                enrichment_data=enrichment_data,
                db=db,
                tenant_id=tenant_id,
                aiohttp_session=aiohttp_session,
                fallback_create_lead_tool_id=create_lead_tool_id,
                default_retry_config=call_lifecycle_config.default_retry_config,
            )

        # Summary
        successful_count = sum(1 for r in results if r.get("success"))
        logger.info(
            f"✅ Post-call actions completed: {successful_count}/{len(results)} successful"
        )

        return {
            "status": "completed",
            "total_actions": len(results),
            "successful": successful_count,
            "failed": len(results) - successful_count,
            "actions": results,
        }

    except Exception as e:
        logger.error(f"Error executing post-call actions: {e}")
        return {"status": "error", "error": str(e), "actions": []}


def _should_execute_action(
    action: PostCallAction,
    customer_exists: bool,
    call_completed_successfully: bool,
    enrichment_success: bool,
    require_enrichment: bool,
) -> bool:
    """
    Determine if an action should execute based on conditions.

    Args:
        action: The action to check
        customer_exists: Whether customer was found in pre-call enrichment
        call_completed_successfully: Whether call ended normally (not abandoned)
        enrichment_success: Whether pre-call enrichment succeeded
        require_enrichment: Whether enrichment is required for post-actions

    Returns:
        True if action should execute, False otherwise
    """
    # Check execution condition
    if action.execution_condition == ActionExecutionCondition.ALWAYS:
        return True
    elif action.execution_condition == ActionExecutionCondition.ON_CUSTOMER_EXISTS:
        return customer_exists
    elif action.execution_condition == ActionExecutionCondition.ON_CUSTOMER_NEW:
        return not customer_exists
    elif action.execution_condition == ActionExecutionCondition.ON_CALL_SUCCESS:
        return call_completed_successfully
    else:
        # Default to execute if unknown condition
        return True


async def _execute_actions_sequential(
    actions: list[PostCallAction],
    session: Session,
    call_summary: dict[str, Any] | None,
    enrichment_data: dict[str, Any] | None,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
    fallback_create_lead_tool_id: str | None = None,
    default_retry_config: PostCallRetryConfig | None = None,
) -> list[dict[str, Any]]:
    """Execute actions sequentially in priority order."""
    results = []

    for action in actions:
        result = await _execute_single_action(
            action=action,
            session=session,
            call_summary=call_summary,
            enrichment_data=enrichment_data,
            db=db,
            tenant_id=tenant_id,
            aiohttp_session=aiohttp_session,
            fallback_create_lead_tool_id=fallback_create_lead_tool_id,
            default_retry_config=default_retry_config,
        )
        results.append(result)

    return results


async def _execute_actions_parallel(
    actions: list[PostCallAction],
    session: Session,
    call_summary: dict[str, Any] | None,
    enrichment_data: dict[str, Any] | None,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
    fallback_create_lead_tool_id: str | None = None,
    default_retry_config: PostCallRetryConfig | None = None,
) -> list[dict[str, Any]]:
    """Execute actions in parallel (faster but no guaranteed order)."""
    tasks = [
        _execute_single_action(
            action=action,
            session=session,
            call_summary=call_summary,
            enrichment_data=enrichment_data,
            db=db,
            tenant_id=tenant_id,
            aiohttp_session=aiohttp_session,
            fallback_create_lead_tool_id=fallback_create_lead_tool_id,
            default_retry_config=default_retry_config,
        )
        for action in actions
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error results
    formatted_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            formatted_results.append({
                "action_type": actions[i].action_type,
                "tool_id": actions[i].tool_id,
                "success": False,
                "error": str(result),
            })
        else:
            formatted_results.append(result)

    return formatted_results


def _is_validation_error(error: str) -> bool:
    """
    Check if an error is a parameter validation error.

    Args:
        error: Error message string

    Returns:
        True if error is a validation error, False otherwise
    """
    validation_keywords = [
        "parameter validation failed",
        "required parameter",
        "is missing",
        "invalid parameter",
        "validation failed",
        "parameter validation",
    ]
    error_lower = error.lower()
    return any(keyword in error_lower for keyword in validation_keywords)


def _is_retryable_api_error(error: str | Exception) -> bool:
    """
    Check if an API error is retryable (timeout, 5xx, network errors).

    Args:
        error: Error message string or Exception object

    Returns:
        True if error is retryable, False otherwise
    """
    error_str = str(error).lower() if isinstance(error, Exception) else error.lower()

    # Non-retryable errors (4xx client errors)
    non_retryable_keywords = [
        "400",  # Bad Request
        "401",  # Unauthorized
        "403",  # Forbidden
        "404",  # Not Found
        "422",  # Unprocessable Entity
        "invalid request",
        "authentication failed",
        "authorization failed",
        "not found",
    ]
    if any(keyword in error_str for keyword in non_retryable_keywords):
        return False

    # Retryable errors (5xx, timeouts, network)
    retryable_keywords = [
        "500",
        "502",
        "503",
        "504",
        "timeout",
        "connection",
        "network",
        "temporary",
        "unavailable",
        "service unavailable",
    ]
    return any(keyword in error_str for keyword in retryable_keywords)


def _get_retry_config(action: PostCallAction, default_retry_config: PostCallRetryConfig | None) -> PostCallRetryConfig:
    """
    Get retry configuration for an action (action-specific or global default).

    Args:
        action: Post-call action
        default_retry_config: Global default retry config

    Returns:
        Retry config to use. Always returns a config (defaults to enabled with sensible defaults if none provided).
    """
    # Use action-specific config if provided (respect enabled/disabled setting)
    if action.retry_config:
        return action.retry_config

    # Use global default if provided (respect enabled/disabled setting)
    if default_retry_config:
        return default_retry_config

    # No retry config - create default with sensible defaults (retries enabled by default)
    return _create_default_retry_config()


def _create_default_retry_config() -> PostCallRetryConfig:
    """
    Create a default retry configuration with sensible defaults.

    Returns:
        Default retry config with retries enabled
    """
    return PostCallRetryConfig(
        enabled=True,
        max_retries=DEFAULT_POST_CALL_RETRY_MAX_ATTEMPTS,
        retry_on_validation_errors=True,
        retry_on_api_errors=True,
        use_llm_for_parameter_fixing=True,
        llm_model=DEFAULT_POST_CALL_RETRY_LLM_MODEL,
        llm_temperature=DEFAULT_POST_CALL_RETRY_LLM_TEMPERATURE,
    )


async def _execute_single_action(
    action: PostCallAction,
    session: Session,
    call_summary: dict[str, Any] | None,
    enrichment_data: dict[str, Any] | None,
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    aiohttp_session: aiohttp.ClientSession,
    fallback_create_lead_tool_id: str | None = None,
    default_retry_config: PostCallRetryConfig | None = None,
) -> dict[str, Any]:
    """
    Execute a single post-call action with retry mechanism and smart fallback.

    Implements intelligent retry with:
    - LLM-based parameter fixing for validation errors
    - Exponential backoff for API errors
    - Configurable retry attempts and behavior

    If UPDATE_CONTACT fails due to missing customer_id, automatically
    falls back to CREATE_LEAD if a fallback tool is configured.

    Args:
        fallback_create_lead_tool_id: Tool ID to use for fallback CREATE_LEAD
        default_retry_config: Global default retry configuration

    Returns:
        Execution result dictionary with retry metadata
    """
    # Get retry configuration
    retry_config = _get_retry_config(action, default_retry_config)

    try:
        logger.debug(
            f"Executing post-call action: {action.action_type} "
            f"(tool: {action.tool_id}, priority: {action.priority})"
        )

        # Load business tool config
        tool_service = BusinessToolService(db, tenant_id)
        tool_config = await tool_service.get_tool(action.tool_id)

        if not tool_config:
            error_msg = f"Business tool {action.tool_id} not found"
            logger.warning(error_msg)
            return {
                "action_type": action.action_type,
                "tool_id": action.tool_id,
                "success": False,
                "error": error_msg,
            }

        # Build parameters from session and enrichment data
        params = _build_action_parameters(session, call_summary, enrichment_data)

        # Execute with retry mechanism
        executor = BusinessToolExecutor(db=db, tenant_id=tenant_id)
        max_retries = retry_config.max_retries
        retry_count = 0
        last_error = None
        last_result = None
        validation_errors = []

        # Build session data for LLM parameter fixing
        session_data = {
            "session_id": session.session_id,
            "call_duration": _calculate_duration(session),
            "phone": params.get("phone"),
            "email": params.get("email"),
            "contact_name": params.get("contact_name"),
        }
        
        # Add detailed call summary information if available
        if call_summary:
            session_data["call_summary"] = {
                "summary": call_summary.get("summary", ""),
                "outcome": call_summary.get("outcome", "Unknown"),
                "reasoning": call_summary.get("reasoning", ""),
            }
        
        # Add hangup reason details from session metadata if available
        if session.metadata:
            # Check for hangup reason in call_metadata
            call_metadata = session.metadata.get("call_metadata", {})
            if call_metadata:
                hangup_info = {
                    "hangup_cause": call_metadata.get("hangup_cause"),
                    "call_status": call_metadata.get("call_status"),
                    "provider": call_metadata.get("provider"),
                }
                # Only add if we have meaningful data
                if any(hangup_info.values()):
                    session_data["hangup_reason"] = {k: v for k, v in hangup_info.items() if v}
            
            # Check for disconnection_reason in metadata (from hangup observer)
            if "disconnection_reason" in session.metadata:
                session_data["hangup_reason"] = session_data.get("hangup_reason", {})
                session_data["hangup_reason"]["disconnection_reason"] = session.metadata.get("disconnection_reason")
                if "hangup_details" in session.metadata:
                    session_data["hangup_reason"]["details"] = session.metadata.get("hangup_details")

        while retry_count <= max_retries:
            try:
                # Execute business tool
                result = await executor.execute_tool(
                    tool_config=tool_config,
                    business_parameters=params,
                    engaging_words="",  # Silent - no TTS output
                    aiohttp_session=aiohttp_session,
                )

                if result.get("success"):
                    logger.info(
                        f"✅ Post-call action {action.action_type} completed successfully "
                        f"(tool: {action.tool_id}, retries: {retry_count})"
                    )
                    return {
                        "action_type": action.action_type,
                        "tool_id": action.tool_id,
                        "priority": action.priority,
                        "success": True,
                        "data": result.get("data"),
                        "retry_count": retry_count,
                    }

                # Action failed - check if we should retry
                error_msg = result.get("error", "Unknown error")
                last_error = error_msg
                last_result = result

                # Extract validation errors if available
                if "validation_details" in result:
                    validation_errors = result.get("validation_details", [])

                # Check if retries are enabled and max retries reached
                if not retry_config.enabled or retry_count >= max_retries:
                    break  # Retries disabled or max retries reached

                is_validation = _is_validation_error(error_msg)
                is_api_error = _is_retryable_api_error(error_msg)

                # Determine if we should retry
                should_retry = False
                if is_validation and retry_config.retry_on_validation_errors:
                    should_retry = True
                    if retry_config.use_llm_for_parameter_fixing:
                        logger.info(
                            f"🔄 Retry {retry_count + 1}/{max_retries}: Validation error detected, "
                            f"using LLM to fix parameters"
                        )
                        try:
                            # Use LLM to fix parameters
                            fixed_params = await fix_parameters_with_llm(
                                tool_config=tool_config,
                                failed_parameters=params,
                                validation_errors=validation_errors if validation_errors else [error_msg],
                                call_summary=call_summary,
                                session_data=session_data,
                                model=retry_config.llm_model,
                                temperature=retry_config.llm_temperature,
                                retry_config=retry_config,
                            )
                            params = fixed_params
                            logger.debug(f"📝 LLM fixed parameters: {list(params.keys())}")
                        except Exception as llm_error:
                            logger.warning(
                                f"⚠️ LLM parameter fixing failed: {llm_error}, "
                                f"proceeding with retry using original parameters"
                            )
                    else:
                        logger.info(
                            f"🔄 Retry {retry_count + 1}/{max_retries}: Validation error detected, "
                            f"but LLM fixing disabled"
                        )
                elif is_api_error and retry_config.retry_on_api_errors:
                    should_retry = True
                    # Calculate exponential backoff delay
                    delay = DEFAULT_POST_CALL_RETRY_DELAY_SECONDS * (EXPONENTIAL_BACKOFF_MULTIPLIER ** retry_count)
                    logger.info(
                        f"🔄 Retry {retry_count + 1}/{max_retries}: API error detected, "
                        f"waiting {delay:.2f}s before retry"
                    )
                    await asyncio.sleep(delay)
                else:
                    # Non-retryable error or retry disabled for this error type
                    logger.debug(f"❌ Error not retryable or retry disabled: {error_msg}")
                    break

                if should_retry:
                    retry_count += 1
                    logger.info(
                        f"🔄 Retrying post-call action {action.action_type} "
                        f"(attempt {retry_count + 1}/{max_retries + 1})"
                    )
                    continue
                else:
                    break

            except Exception as e:
                # Exception during execution
                last_error = str(e)
                logger.error(f"Exception during post-call action execution: {e}")

                # Check if retryable
                if retry_config.enabled and retry_count < max_retries and _is_retryable_api_error(e):
                    retry_count += 1
                    delay = DEFAULT_POST_CALL_RETRY_DELAY_SECONDS * (EXPONENTIAL_BACKOFF_MULTIPLIER ** (retry_count - 1))
                    logger.info(
                        f"🔄 Retry {retry_count}/{max_retries}: Exception occurred, "
                        f"waiting {delay:.2f}s before retry"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Retries disabled, not retryable, or max retries reached
                    break

        # All retries exhausted or error not retryable
        error_msg = last_error or "Unknown error"
        logger.warning(
            f"❌ Post-call action {action.action_type} failed after {retry_count} retries "
            f"(tool: {action.tool_id}): {error_msg}"
        )

        # Smart fallback: If UPDATE_CONTACT fails due to missing customer_id, try CREATE_LEAD
        should_fallback = (
            action.action_type == CRMActionType.UPDATE_CONTACT
            and fallback_create_lead_tool_id
            and "customer_id" in error_msg.lower()
        )

        if should_fallback:
            logger.info(
                f"🔄 UPDATE_CONTACT failed due to missing customer_id, "
                f"falling back to CREATE_LEAD (tool: {fallback_create_lead_tool_id})"
            )

            # Get CREATE_LEAD tool
            fallback_tool_config = await tool_service.get_tool(fallback_create_lead_tool_id)

            if fallback_tool_config:
                # Remove customer_id from params (not needed for CREATE_LEAD)
                fallback_params = {k: v for k, v in params.items() if k != "customer_id"}

                fallback_result = await executor.execute_tool(
                    tool_config=fallback_tool_config,
                    business_parameters=fallback_params,
                    engaging_words="",
                    aiohttp_session=aiohttp_session,
                )

                if fallback_result.get("success"):
                    logger.info(
                        f"✅ Fallback CREATE_LEAD succeeded after UPDATE_CONTACT failed "
                        f"(tool: {fallback_create_lead_tool_id})"
                    )
                    return {
                        "action_type": CRMActionType.CREATE_LEAD,
                        "tool_id": fallback_create_lead_tool_id,
                        "priority": action.priority,
                        "success": True,
                        "data": fallback_result.get("data"),
                        "fallback_from": action.action_type,
                        "original_error": error_msg,
                        "retry_count": retry_count,
                    }
                else:
                    logger.warning(
                        f"❌ Fallback CREATE_LEAD also failed: {fallback_result.get('error')}"
                    )

        return {
            "action_type": action.action_type,
            "tool_id": action.tool_id,
            "priority": action.priority,
            "success": False,
            "data": last_result.get("data") if last_result else None,
            "error": error_msg,
            "retry_count": retry_count,
            "retry_exhausted": retry_count >= max_retries,
        }

    except Exception as e:
        logger.error(f"Error executing post-call action {action.action_type}: {e}")
        return {
            "action_type": action.action_type,
            "tool_id": action.tool_id,
            "success": False,
            "error": str(e),
            "retry_count": 0,
        }


def _build_action_parameters(
    session: Session,
    call_summary: dict[str, Any] | None,
    enrichment_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build parameters for post-call action from session data.

    Aggregates:
    - Session metadata (ID, duration, timestamps)
    - User/contact information (phone for telephony, email for WebRTC)
    - Call summary (if available) - includes summary, outcome, reasoning/call_notes
    - Enrichment data (if available) - includes customer_id, firstname, lastname

    Returns:
        Dictionary of parameters for business tool execution
    """
    params: dict[str, Any] = {}

    # Session metadata
    params["session_id"] = session.session_id
    params["call_started_at"] = session.created_at.isoformat() if session.created_at else None
    params["call_ended_at"] = session.updated_at.isoformat() if session.updated_at else None
    params["call_duration"] = _calculate_duration(session)

    # User/contact information - Transport-specific extraction
    # WebRTC: email from created_by (created_by is the actual user)
    # Telephony: phone_number from participants (created_by is the operator, not the customer)

    # Determine transport type
    is_telephony = session.transport in ["twilio", "plivo"]

    # Extract from created_by (WebRTC sessions only - created_by is the actual user)
    # For telephony calls, created_by contains operator info, not customer info
    # We should NOT use created_by.email for telephony calls
    if session.created_by and not is_telephony:
        # WebRTC: created_by is the actual user
        if session.created_by.email:
            params["email"] = session.created_by.email
        if session.created_by.name:
            params["contact_name"] = session.created_by.name

    # Extract from participants (Telephony sessions - this is the actual customer)
    if session.participants:
        for participant in session.participants:
            if participant.role == "user":
                # Telephony: phone_number field (this is the actual customer)
                if participant.phone_number:
                    params["phone"] = participant.phone_number
                # Name from participants (this is the actual customer name)
                if participant.name and "contact_name" not in params:
                    params["contact_name"] = participant.name

    # Call summary (if summarization was enabled)
    # Extract basic summary fields first
    if call_summary:
        params["summary"] = call_summary.get("summary", "")
        params["outcome"] = call_summary.get("outcome", "Unknown")
        params["call_notes"] = call_summary.get("reasoning", "")
        
        # Add full summary object for reference (enhanced details)
        params["call_summary_full"] = call_summary
        
        # Add any additional summary fields
        for key in ["sentiment", "key_points", "action_items", "follow_up"]:
            if key in call_summary:
                params[f"summary_{key}"] = call_summary[key]

    # Enrichment data (e.g., customer_id from pre-call lookup)
    if enrichment_data:
        # Extract customer_id from contact object if available
        if "contact" in enrichment_data and isinstance(enrichment_data["contact"], dict):
            contact = enrichment_data["contact"]
            # Extract customer_id (prefer id, fallback to hs_object_id)
            if "id" in contact:
                params["customer_id"] = contact["id"]
            elif "hs_object_id" in contact:
                params["customer_id"] = contact["hs_object_id"]
            
            # Extract firstname and lastname if available
            if "firstname" in contact and contact["firstname"]:
                params["firstname"] = contact["firstname"]
            if "lastname" in contact and contact["lastname"]:
                params["lastname"] = contact["lastname"]
            
            # Prefer enrichment email if available and not already set
            if "email" in contact and contact["email"] and "email" not in params:
                params["email"] = contact["email"]
        
        # Add customer_id if directly available (backward compatibility)
        if "customer_id" in enrichment_data:
            params["customer_id"] = enrichment_data["customer_id"]

        # Add enrichment name if not already set
        if "name" in enrichment_data and "contact_name" not in params:
            params["contact_name"] = enrichment_data["name"]

        # Add other enrichment data with prefix to avoid conflicts
        for key, value in enrichment_data.items():
            if key not in params and key not in ["name", "customer_id", "contact"]:  # Don't overwrite or duplicate
                params[f"enrichment_{key}"] = value

    # Session metadata from session object
    if session.metadata:
        # Add transcript if available
        if "transcript" in session.metadata:
            params["transcript"] = session.metadata["transcript"]

    # Debug log to show extracted parameters
    logger.debug(
        f"Built post-call action parameters: "
        f"session={session.session_id}, "
        f"transport={session.transport}, "
        f"has_email={'email' in params}, "
        f"has_phone={'phone' in params}, "
        f"has_customer_id={'customer_id' in params}"
    )

    return params


def _calculate_duration(session: Session) -> int:
    """
    Calculate call duration in seconds.

    Args:
        session: Session object

    Returns:
        Duration in seconds, or 0 if timestamps not available
    """
    if session.created_at and session.updated_at:
        delta = session.updated_at - session.created_at
        return int(delta.total_seconds())
    return 0
