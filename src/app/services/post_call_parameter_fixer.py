"""
LLM-based parameter fixing service for post-call actions.

This service uses LLM to intelligently fix missing or invalid parameters
when post-call actions fail due to validation errors.
Similar to how call summarization works, this service uses OpenAI
to generate appropriate parameter values from call context.
"""

import json
from typing import Any

import openai
from loguru import logger

from app.core import settings
from app.core.constants import (
    DEFAULT_POST_CALL_RETRY_LLM_MODEL,
    DEFAULT_POST_CALL_RETRY_LLM_TEMPERATURE,
    DEFAULT_POST_CALL_RETRY_LLM_SYSTEM_PROMPT_TEMPLATE,
)
from app.schemas.core.business_tool_schema import BusinessTool
from app.schemas.core.call_lifecycle_schema import PostCallRetryConfig


async def fix_parameters_with_llm(
    tool_config: BusinessTool,
    failed_parameters: dict[str, Any],
    validation_errors: list[str],
    call_summary: dict[str, Any] | None,
    session_data: dict[str, Any],
    model: str = DEFAULT_POST_CALL_RETRY_LLM_MODEL,
    temperature: float = DEFAULT_POST_CALL_RETRY_LLM_TEMPERATURE,
    retry_config: PostCallRetryConfig | None = None,
) -> dict[str, Any]:
    """
    Use LLM to fix missing or invalid parameters for post-call actions.

    Analyzes the tool configuration, validation errors, call summary, and session data
    to generate appropriate parameter values that will pass validation.

    Args:
        tool_config: The business tool configuration that failed
        failed_parameters: The parameters that were provided (may be incomplete or invalid)
        validation_errors: List of validation error messages
        call_summary: AI-generated call summary (if available)
        session_data: Session metadata (duration, timestamps, etc.)
        model: LLM model to use (default: gpt-4o-mini)
        temperature: LLM temperature for generation (default: 0.3)
        retry_config: Optional retry configuration. If provided and contains llm_system_prompt,
                     uses that custom prompt template instead of the default from constants.

    Returns:
        Dictionary of fixed parameters ready for retry

    Raises:
        Exception: If LLM call fails or response is invalid
    """
    try:
        logger.info(f"🤖 Using LLM to fix parameters for tool: {tool_config.name}")

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Build parameter descriptions for the LLM
        parameter_descriptions = []
        for param in tool_config.parameters:
            param_info = {
                "name": param.name,
                "type": param.type,
                "required": param.required,
                "description": param.description,
            }
            if param.examples:
                param_info["examples"] = param.examples[:3]  # Limit examples
            parameter_descriptions.append(param_info)

        # Build context from call summary and session data
        context_parts = []

        if call_summary:
            context_parts.append(f"Call Summary: {json.dumps(call_summary, indent=2)}")

        if session_data:
            # Extract relevant session info
            session_info = {
                "session_id": session_data.get("session_id"),
                "call_duration": session_data.get("call_duration"),
                "phone": session_data.get("phone"),
                "email": session_data.get("email"),
                "contact_name": session_data.get("contact_name"),
            }
            
            # Add detailed call summary if available (may be more detailed than call_summary parameter)
            if "call_summary" in session_data:
                session_info["call_summary_details"] = session_data["call_summary"]
            
            # Add hangup reason details if available
            if "hangup_reason" in session_data:
                session_info["hangup_reason"] = session_data["hangup_reason"]
            
            # Remove None values
            session_info = {k: v for k, v in session_info.items() if v is not None}
            if session_info:
                context_parts.append(f"Session Context: {json.dumps(session_info, indent=2)}")

        # Extract enrichment data from failed_parameters if available
        # Look for all enrichment_* fields (enrichment_contact, enrichment_notes, enrichment_found, enrichment_message, etc.)
        enrichment_data = {}
        for key, value in failed_parameters.items():
            if key.startswith("enrichment_"):
                # Remove the "enrichment_" prefix for the context
                clean_key = key.replace("enrichment_", "")
                if isinstance(value, dict):
                    enrichment_data[clean_key] = value
                else:
                    enrichment_data[clean_key] = value

        if enrichment_data:
            context_parts.append(f"Enrichment Data (CRM lookup results): {json.dumps(enrichment_data, indent=2)}")
            
            # Add explicit warning if contact was not found
            if enrichment_data.get("found") is False:
                context_parts.append(
                    "⚠️ IMPORTANT: Contact was NOT FOUND in CRM (found: false). "
                    "Do NOT generate fake customer_id values. Only extract customer_id if it exists in enrichment_contact."
                )

        context_text = "\n\n".join(context_parts) if context_parts else "No call summary or session context available."

        # Clean failed_parameters by removing template placeholders and non-parameter fields
        cleaned_parameters = {}
        for key, value in failed_parameters.items():
            # Skip template placeholders (they need to be replaced with actual values)
            if isinstance(value, str):
                # Remove if value is exactly a template placeholder like {{param}}
                if value.startswith("{{") and value.endswith("}}"):
                    continue
                # Remove if value contains template placeholder syntax anywhere
                if "{{" in value or "}}" in value:
                    continue
            # Skip enrichment_* prefixed fields (they're in context, not direct parameters)
            if key.startswith("enrichment_"):
                continue
            # Keep other parameters
            cleaned_parameters[key] = value

        # Get system prompt template (from retry_config if provided, otherwise from constants)
        prompt_template = DEFAULT_POST_CALL_RETRY_LLM_SYSTEM_PROMPT_TEMPLATE
        if retry_config and retry_config.llm_system_prompt:
            prompt_template = retry_config.llm_system_prompt
            logger.debug(f"Using custom system prompt from retry_config for tool: {tool_config.name}")
        else:
            logger.debug(f"Using default system prompt from constants for tool: {tool_config.name}")

        # Build the system prompt by formatting the template
        system_prompt = prompt_template.format(
            tool_name=tool_config.name,
            tool_description=tool_config.description,
            parameter_descriptions=json.dumps(parameter_descriptions, indent=2),
            validation_errors=chr(10).join(f"- {error}" for error in validation_errors),
            cleaned_parameters=json.dumps(cleaned_parameters, indent=2),
            context_text=context_text,
        )

        # Build user message
        user_message = """Please generate the corrected parameters that will pass validation. Return only the JSON object with the fixed parameters."""

        messages_for_api = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        logger.debug(f"Calling LLM ({model}) to fix parameters for {tool_config.name}")

        response = await client.chat.completions.create(
            model=model,
            messages=messages_for_api,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        fixed_params_content = response.choices[0].message.content

        # Parse the JSON response
        try:
            fixed_parameters = json.loads(fixed_params_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"LLM response content: {fixed_params_content}")
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

        # Merge with cleaned parameters (LLM output should override)
        # Start with cleaned_parameters as base (excluding template placeholders and enrichment_* fields)
        # Then update with LLM fixes
        corrected_parameters = cleaned_parameters.copy()
        corrected_parameters.update(fixed_parameters)
        
        # Get valid parameter names from tool schema
        valid_param_names = {param.name for param in tool_config.parameters}
        
        # Post-process: Clean up parameters
        for key, value in list(corrected_parameters.items()):
            # CRITICAL: Remove any parameter NOT in the tool's schema
            if key not in valid_param_names:
                logger.warning(f"Removing parameter not in tool schema: {key}")
                corrected_parameters.pop(key)
                continue
            
            # CRITICAL: Remove ANY value that contains template placeholders ({{ or }})
            if isinstance(value, str):
                if "{{" in value or "}}" in value:
                    logger.warning(f"Removing parameter with template placeholder: {key}={value}")
                    corrected_parameters.pop(key)
                    continue
                
                # Also check for template placeholders that are the entire value
                if value.startswith("{{") and value.endswith("}}"):
                    logger.warning(f"Removing unreplaced template placeholder: {key}={value}")
                    corrected_parameters.pop(key)
                    continue
            
            # Detect and remove fake/placeholder values that LLM might generate
            if isinstance(value, str):
                # Common fake patterns to detect
                fake_patterns = [
                    "CUST-",  # Fake customer IDs like "CUST-12345"
                    "PLACEHOLDER",
                    "N/A",
                    "NULL",
                    "EXAMPLE",
                    "TEST_",
                ]
                value_upper = value.upper()
                if any(pattern in value_upper for pattern in fake_patterns):
                    # Check if it's a reasonable value (e.g., "CUST-12345" is fake, but "CUST-REAL-ID" might be okay)
                    # If it matches common fake patterns exactly, remove it
                    if key == "customer_id" and value_upper.startswith("CUST-") and len(value) < 15:
                        logger.warning(f"Removing likely fake {key} value: {value}")
                        corrected_parameters.pop(key)
                        continue

        logger.info(f"✅ LLM fixed parameters for {tool_config.name}: {list(corrected_parameters.keys())}")
        logger.debug(f"LLM-generated parameters: {json.dumps(corrected_parameters, indent=2)}")

        return corrected_parameters

    except openai.APIError as e:
        logger.error(f"OpenAI API error while fixing parameters: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fixing parameters with LLM: {e}")
        raise

