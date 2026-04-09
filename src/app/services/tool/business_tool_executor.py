"""
Simplified Business Tool Executor

This service executes business tools by making API calls with the simplified schema.
Complex transformations and workflows have been removed for simplicity.
"""

import json
import time
from datetime import datetime
from typing import Any

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.core.business_tool_schema import (
    APIConfig,
    BusinessTool,
    FieldType,
)
from app.services.ai_engaging_words_service import AIEngagingWordsService
from app.services.tool.authentication_handler import AuthenticationHandler
from app.tools.engaging_words_config import validate_engaging_words
from app.utils.field_type_utils import field_type_to_validation_string
from app.utils.validation.field_validators import validate_field_value


class BusinessToolExecutor:
    """Simplified executor for business tools - handles API calls and response processing."""

    def __init__(self, llm_service=None, db: AsyncIOMotorDatabase | None = None, tenant_id: str | None = None, agent=None):
        """Initialize Business Tool Executor.

        Args:
            llm_service: LLM service for AI-enhanced engaging words.
            db: MongoDB database instance (required for custom_token_db auth).
            tenant_id: Tenant ID (required for custom_token_db auth).
            agent: BaseAgent instance for accessing session-scoped pre-request cache.
        """
        self.auth_handler = AuthenticationHandler(db=db, tenant_id=tenant_id)
        self.ai_engaging_service = AIEngagingWordsService(llm_service)
        self.agent = agent  # Store agent reference for cache access
        logger.debug(f"BusinessToolExecutor initialized (db: {db is not None}, tenant_id: {tenant_id}, agent: {agent is not None})")

    async def execute_tool(self, tool_config: BusinessTool, business_parameters: dict[str, Any], engaging_words: str, aiohttp_session: aiohttp.ClientSession, params=None) -> dict[str, Any]:
        """
        Execute a business tool with the provided parameters.

        Args:
            tool_config: The business tool configuration
            business_parameters: Parameters provided by the AI
            engaging_words: Words to speak during execution
            aiohttp_session: HTTP session for making requests
            params: Optional FunctionCallParams for speaking engaging words

        Returns:
            Result dictionary with success/error information
        """
        start_time = time.time()

        try:
            logger.info(f"Executing business tool: {tool_config.name}")
            logger.debug(f"Parameters: {business_parameters}")

            # Generate enhanced engaging words if needed
            enhanced_engaging_words = await self._get_enhanced_engaging_words(tool_config, business_parameters, engaging_words)
            logger.debug(f"Using engaging words: {enhanced_engaging_words}")

            # Enhanced parameter validation and transformation
            validation_result = await self._validate_and_transform_parameters(business_parameters, tool_config.parameters)

            if not validation_result["valid"]:
                return {"success": False, "error": validation_result["error"], "execution_time_ms": (time.time() - start_time) * 1000, "validation_details": validation_result.get("details", [])}

            # Speak engaging words AFTER validation passes (so we don't speak for invalid calls)
            if params and enhanced_engaging_words and enhanced_engaging_words.strip():
                try:
                    from pipecat.frames.frames import TTSSpeakFrame
                    await params.llm.push_frame(TTSSpeakFrame(enhanced_engaging_words))
                    logger.debug(f"🔊 Speaking engaging words after validation: '{enhanced_engaging_words}'")
                except Exception as e:
                    logger.warning(f"Failed to speak engaging words: {e}")

            # Use validated and transformed parameters
            validated_parameters = validation_result["parameters"]

            # Apply basic transformations for common use cases
            transformed_parameters = await self._apply_basic_transformations(validated_parameters)

            # Get authentication headers and extract token values for use in templates
            # This allows pre-requests and main API call to use {{auth_token}} in body templates
            auth_headers = await self.auth_handler.get_headers(tool_config.api_config.authentication, aiohttp_session=aiohttp_session)

            # Extract token values from headers for use in body templates
            auth_token_params = {}
            if auth_headers:
                # Extract token from Authorization header (Bearer, Basic, etc.)
                if "Authorization" in auth_headers:
                    auth_value = auth_headers["Authorization"]
                    # Remove "Bearer " prefix if present
                    if auth_value.startswith("Bearer "):
                        auth_token_params["auth_token"] = auth_value.replace("Bearer ", "", 1)
                    elif auth_value.startswith("Basic "):
                        auth_token_params["auth_token"] = auth_value.replace("Basic ", "", 1)
                    else:
                        auth_token_params["auth_token"] = auth_value
                    logger.debug(f"Extracted auth_token for use in templates (length: {len(auth_token_params.get('auth_token', ''))})")

                # Extract any other token headers (e.g., X-API-Key, X-ID-Token)
                for header_name, header_value in auth_headers.items():
                    if header_name != "Authorization" and any(keyword in header_name.lower() for keyword in ["token", "key", "auth"]):
                        # Convert header name to snake_case parameter name (e.g., X-ID-Token -> x_id_token)
                        param_name = header_name.lower().replace("-", "_")
                        auth_token_params[param_name] = header_value
                        logger.debug(f"Extracted {param_name} for use in templates")

            # Merge auth tokens with parameters for pre-requests and main call
            parameters_with_auth = {**transformed_parameters, **auth_token_params}

            # Execute pre-requests if configured (for multi-step workflows)
            pre_request_data = {}
            pre_request_details = []
            logger.debug(f"🔍 Checking pre_requests: {tool_config.pre_requests}")
            logger.debug(f"🔍 Pre_requests count: {len(tool_config.pre_requests) if tool_config.pre_requests else 0}")
            if tool_config.pre_requests:
                logger.info(f"Executing {len(tool_config.pre_requests)} pre-request(s) for multi-step workflow")
                pre_request_result = await self._execute_pre_requests(
                    tool_config.pre_requests,
                    tool_config.api_config,
                    parameters_with_auth,  # Pass parameters with auth tokens
                    aiohttp_session
                )

                if not pre_request_result["success"]:
                    # Pre-request failed - return error immediately
                    return {
                        "success": False,
                        "error": pre_request_result["error"],
                        "error_type": "PreRequestError",
                        "failed_pre_request": pre_request_result.get("failed_pre_request"),
                        "execution_time_ms": (time.time() - start_time) * 1000,
                        "pre_requests_executed": pre_request_result.get("pre_requests_executed", []),
                    }

                pre_request_data = pre_request_result["extracted_data"]
                pre_request_details = pre_request_result["pre_requests_executed"]
                logger.debug(f"Pre-requests completed. Extracted data: {pre_request_data}")

            # Merge all data for main call: auth tokens + pre-request results + original parameters
            merged_parameters = {**transformed_parameters, **auth_token_params, "pre_request": pre_request_data}

            # Execute the API call
            result = await self._execute_api_call(tool_config.api_config, merged_parameters, aiohttp_session)

            # Process the response (pass business parameters for template substitution)
            processed_result = await self._process_response(result, tool_config.api_config, transformed_parameters)

            execution_time = (time.time() - start_time) * 1000
            processed_result["execution_time_ms"] = execution_time
            processed_result["engaging_words_used"] = enhanced_engaging_words
            processed_result["engaging_words_original"] = engaging_words

            # Add pre-request execution details if any
            if pre_request_details:
                processed_result["pre_requests_executed"] = pre_request_details

            # Add insights for analytics
            insights = self.ai_engaging_service.get_insights_summary(tool_config, business_parameters)
            processed_result["tool_insights"] = insights

            logger.info(f"Tool execution completed in {execution_time:.0f}ms")
            return processed_result

        except Exception as e:
            logger.error(f"Error executing business tool {tool_config.name}: {e}")
            return {"success": False, "error": f"Execution failed: {e!s}", "execution_time_ms": (time.time() - start_time) * 1000}

    async def _execute_api_call(self, api_config: APIConfig, parameters: dict[str, Any], aiohttp_session: aiohttp.ClientSession) -> dict[str, Any]:
        """Execute the actual API call."""

        try:
            # Build URL with template substitution for endpoint path
            endpoint = api_config.endpoint.lstrip('/')
            # Apply template substitution to endpoint path (e.g., /api/contacts/{{customer_id}})
            if "{{" in endpoint:
                endpoint = self._apply_string_template(endpoint, parameters)
                # Check if endpoint still has unreplaced placeholders (critical error)
                if "{{" in endpoint or "}}" in endpoint:
                    error_msg = f"Endpoint path contains unreplaced template placeholders: {endpoint}"
                    logger.error(error_msg)
                    return {"status_code": 400, "data": {"error": error_msg}, "success": False}
            url = f"{api_config.base_url.rstrip('/')}/{endpoint}"

            # Add query parameters with template substitution
            if api_config.query_params:
                # Apply template substitution to query parameters
                processed_query_params = {}
                for key, value in api_config.query_params.items():
                    if isinstance(value, str) and "{{" in value:
                        # Apply parameter substitution
                        processed_value = self._apply_string_template(value, parameters)
                        # Remove parameter if it still contains template placeholders (optional parameter)
                        if isinstance(processed_value, str) and ("{{" in processed_value or "}}" in processed_value):
                            logger.debug(f"Skipping query parameter '{key}' with unreplaced template placeholder: {processed_value}")
                            continue
                        processed_query_params[key] = processed_value
                    else:
                        processed_query_params[key] = value

                # Only add query string if we have parameters
                if processed_query_params:
                    # Build query string with URL encoding
                    from urllib.parse import urlencode

                    query_string = urlencode(processed_query_params)
                    url = f"{url}?{query_string}"

            # Get authentication headers
            headers = await self.auth_handler.get_headers(api_config.authentication, aiohttp_session)
            headers["Content-Type"] = "application/json"

            # Build request body from template
            # Note: _apply_template already cleans placeholders internally
            body = None
            if api_config.body_template:
                body = self._apply_template(api_config.body_template, parameters)

            logger.debug(f"API call: {api_config.method} {url} (timeout: {api_config.timeout_seconds}s)")
            logger.info(f"API call: {api_config.method} {url} (timeout: {api_config.timeout_seconds}s)")
            logger.debug(f"Body: {body}")
            # Convert body to string before slicing (body is a dict, not a string)
            body_str = str(body) if body else "None"
            logger.info(f"Body: {body_str[:200]}")

            # Make the API call with configured timeout
            timeout = aiohttp.ClientTimeout(total=api_config.timeout_seconds)

            async with aiohttp_session.request(method=api_config.method, url=url, headers=headers, json=body, timeout=timeout) as response:
                status_code = response.status

                try:
                    response_data = await response.json()
                except (ValueError, Exception):  # JSON parsing errors
                    response_data = {"text": await response.text()}

                logger.debug(f"API response: Status {status_code}, Data: {response_data}")
                # Convert response_data to string before slicing (response_data might be a dict)
                response_str = str(response_data)
                logger.info(f"API response: Status {status_code}, Data: {response_str[:200]}")   

                return {"status_code": status_code, "data": response_data, "success": 200 <= status_code < 300}

        except aiohttp.ClientError as e:
            if "timeout" in str(e).lower():
                error_msg = f"API request timed out after {api_config.timeout_seconds} seconds"
                logger.warning(f"Timeout error for {url}: {error_msg}")
                return {"status_code": 408, "data": {"error": error_msg}, "success": False}
            else:
                error_msg = f"Network error: {e!s}"
                logger.warning(f"Client error for {url}: {error_msg}")
                return {"status_code": 500, "data": {"error": error_msg}, "success": False}
        except Exception as e:
            error_msg = f"Unexpected error during API call: {e!s}"
            logger.error(f"Unexpected error for {url}: {error_msg}")
            return {"status_code": 500, "data": {"error": error_msg}, "success": False}

    def _apply_template(self, template: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
        """Apply parameter values to a template, supporting nested object access.
        
        Supports placeholders like:
        - {{param_name}} - simple parameter
        - {{pre_request.sender_id}} - nested object access
        - {{auth_token}} - authentication token
        """
        import re

        template_str = json.dumps(template)

        # Find all placeholders in template
        placeholders = re.findall(r"\{\{([^\}]+)\}\}", template_str)

        for placeholder_content in placeholders:
            placeholder = f"{{{{{placeholder_content}}}}}"

            try:
                # Check if it's a nested path (contains dots)
                if "." in placeholder_content:
                    # Navigate nested object
                    value = self._get_nested_value(parameters, placeholder_content)
                else:
                    # Simple parameter lookup
                    value = parameters.get(placeholder_content)

                if value is not None:
                    # Convert value to string for replacement
                    value_str = json.dumps(value) if not isinstance(value, str) else f'"{value}"'
                    template_str = template_str.replace(f'"{placeholder}"', value_str)
                    template_str = template_str.replace(placeholder, str(value))
                else:
                    logger.debug(f"Placeholder '{placeholder_content}' not found in parameters")

            except Exception as e:
                logger.warning(f"Failed to resolve placeholder '{placeholder_content}': {e}")

        try:
            result = json.loads(template_str)
            # Remove any remaining template placeholders from the result
            return self._clean_body_from_placeholders(result)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse template after substitution: {template_str[:200]}")
            return template

    def _clean_body_from_placeholders(self, body: Any) -> Any:
        """Remove any parameters that contain template placeholders ({{ or }}).
        
        This ensures that unreplaced template placeholders are not sent in API requests.
        For optional parameters, if they contain placeholders, they are removed entirely.
        
        Args:
            body: The request body (dict, list, or primitive value)
            
        Returns:
            Cleaned body with no template placeholders
        """
        if isinstance(body, dict):
            cleaned = {}
            for key, value in body.items():
                # Recursively clean nested structures
                cleaned_value = self._clean_body_from_placeholders(value)
                
                # Skip if value contains template placeholders
                if isinstance(cleaned_value, str):
                    if "{{" in cleaned_value or "}}" in cleaned_value:
                        logger.debug(f"Removing parameter '{key}' with template placeholder: {cleaned_value}")
                        continue
                
                # Skip None values for optional parameters
                if cleaned_value is None:
                    continue
                
                cleaned[key] = cleaned_value
            return cleaned
        elif isinstance(body, list):
            cleaned = []
            for item in body:
                cleaned_item = self._clean_body_from_placeholders(item)
                # Skip items with template placeholders or None values
                if isinstance(cleaned_item, str):
                    if "{{" in cleaned_item or "}}" in cleaned_item:
                        logger.debug(f"Removing list item with template placeholder: {cleaned_item}")
                        continue
                if cleaned_item is None:
                    continue
                cleaned.append(cleaned_item)
            return cleaned
        elif isinstance(body, str):
            # If string contains template placeholders, return None (will be filtered out)
            if "{{" in body or "}}" in body:
                return None
            return body
        else:
            # Primitive types (int, float, bool, None) - return as-is
            return body

    def _get_nested_value(self, data: dict, path: str) -> Any:
        """Get a nested value from a dictionary using dot notation.
        
        Args:
            data: Dictionary to search in
            path: Path like "pre_request.sender_id" or "data.user.id"
            
        Returns:
            Value at the path
            
        Raises:
            KeyError: If path not found
        """
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            else:
                raise KeyError(f"Cannot access '{part}' on non-dict value")

        return current

    async def _execute_pre_requests(self, pre_requests: list, api_config, parameters: dict[str, Any], aiohttp_session: aiohttp.ClientSession) -> dict[str, Any]:
        """Execute all pre-requests sequentially and extract required fields.

        Args:
            pre_requests: List of PreRequestConfig objects
            api_config: Main API configuration (for base_url and auth)
            parameters: Current parameters (for template substitution)
            aiohttp_session: HTTP session for requests

        Returns:
            Result dictionary with extracted data or error
        """
        extracted_data = {}
        pre_requests_executed = []

        for pre_request in pre_requests:
            logger.info(f"Processing pre-request: {pre_request.name}")

            # Check if caching is enabled for this pre-request
            if pre_request.cache_config and pre_request.cache_config.enabled and self.agent:
                cache_key = pre_request.cache_config.cache_key or f"pre_req:{pre_request.name}"

                # Try to get from cache
                cached_result = self.agent.get_cached_pre_request(cache_key)
                if cached_result:
                    logger.info(f"Using CACHED pre-request result for: {pre_request.name}")
                    extracted_data.update(cached_result)

                    # Add to execution details with actual cached values for visibility
                    pre_requests_executed.append(
                        {
                            "name": pre_request.name,
                            "cached": True,
                            "cache_key": cache_key,
                            "extracted_fields": list(cached_result.keys()),
                            "extracted_values": cached_result,
                            "execution_time_ms": 0,
                        }
                    )
                    continue  # Skip execution, use cached data

            # Execute pre-request (not cached or cache miss)
            logger.info(f"Executing pre-request: {pre_request.name}")
            pre_request_start = time.time()

            try:
                # Execute the pre-request with current parameters and already-extracted data
                merged_params = {**parameters, "pre_request": extracted_data}
                result = await self._execute_single_pre_request(pre_request, api_config, merged_params, aiohttp_session)

                pre_request_time = (time.time() - pre_request_start) * 1000

                if not result["success"]:
                    logger.error(f"Pre-request '{pre_request.name}' failed: {result.get('error')}")
                    return {
                        "success": False,
                        "error": f"Pre-request '{pre_request.name}' failed: {result.get('error')}",
                        "failed_pre_request": pre_request.name,
                        "pre_requests_executed": pre_requests_executed,
                    }

                # Extract required fields from response
                response_data = result.get("data", {})
                extracted_fields = {}

                for field_name, json_path in pre_request.extract_fields.items():
                    try:
                        extracted_value = self._extract_field_from_response(response_data, json_path)
                        extracted_fields[field_name] = extracted_value
                        logger.debug(f"Extracted field '{field_name}' = '{extracted_value}' from path '{json_path}'")
                    except ValueError as e:
                        logger.error(f"Failed to extract field '{field_name}' from pre-request '{pre_request.name}': {e}")
                        return {
                            "success": False,
                            "error": f"Pre-request '{pre_request.name}' did not return expected field '{field_name}'. Path: '{json_path}'. Error: {e!s}",
                            "failed_pre_request": pre_request.name,
                            "available_fields": list(response_data.keys()) if isinstance(response_data, dict) else [],
                            "response_sample": str(response_data)[:200],
                            "pre_requests_executed": pre_requests_executed,
                        }

                # Add extracted fields to accumulated data
                extracted_data.update(extracted_fields)

                # Cache the result if enabled
                if pre_request.cache_config and pre_request.cache_config.enabled and self.agent:
                    cache_key = pre_request.cache_config.cache_key or f"pre_req:{pre_request.name}"
                    await self.agent.set_cached_pre_request(cache_key, extracted_fields)

                # Record pre-request execution details
                pre_requests_executed.append(
                    {
                        "name": pre_request.name,
                        "cached": False,
                        "execution_time_ms": pre_request_time,
                        "extracted_fields": list(extracted_fields.keys()),
                        "extracted_values": extracted_fields,
                        "status_code": result.get("status_code"),
                    }
                )

                logger.info(f"Pre-request '{pre_request.name}' completed in {pre_request_time:.0f}ms. Extracted: {list(extracted_fields.keys())}")

            except Exception as e:
                logger.error(f"Exception during pre-request '{pre_request.name}': {e}")
                return {"success": False, "error": f"Pre-request '{pre_request.name}' raised exception: {e!s}", "failed_pre_request": pre_request.name, "pre_requests_executed": pre_requests_executed}

        logger.info(f"All {len(pre_requests)} pre-request(s) completed successfully")
        return {"success": True, "extracted_data": extracted_data, "pre_requests_executed": pre_requests_executed}

    async def _execute_single_pre_request(self, pre_request, api_config, parameters: dict[str, Any], aiohttp_session: aiohttp.ClientSession) -> dict[str, Any]:
        """Execute a single pre-request.

        Args:
            pre_request: PreRequestConfig object
            api_config: Main API configuration (for base_url and auth)
            parameters: Parameters including already-extracted pre-request data
            aiohttp_session: HTTP session

        Returns:
            Result dictionary with response data
        """
        try:
            # Build URL (use main api_config.base_url)
            url = f"{api_config.base_url.rstrip('/')}/{pre_request.endpoint.lstrip('/')}"

            # Add query parameters if specified
            if pre_request.query_params:
                processed_query_params = {}
                for key, value in pre_request.query_params.items():
                    if isinstance(value, str) and "{{" in value:
                        processed_value = self._apply_string_template(value, parameters)
                        processed_query_params[key] = processed_value
                    else:
                        processed_query_params[key] = value

                from urllib.parse import urlencode

                query_string = urlencode(processed_query_params)
                url = f"{url}?{query_string}"

            # Get authentication headers (same as main call)
            headers = await self.auth_handler.get_headers(api_config.authentication, aiohttp_session=aiohttp_session)
            headers["Content-Type"] = "application/json"

            # Add any custom headers from pre-request config
            if pre_request.headers:
                for header_name, header_value in pre_request.headers.items():
                    if "{{" in header_value:
                        header_value = self._apply_string_template(header_value, parameters)
                    headers[header_name] = header_value

            # Build request body from template
            body = None
            if pre_request.body_template:
                logger.debug(f"🔍 Pre-request parameters keys before template: {list(parameters.keys())}")
                logger.debug(f"🔍 Pre-request has auth_token: {'auth_token' in parameters}")
                body = self._apply_template(pre_request.body_template, parameters)

            logger.debug(f"Pre-request {pre_request.name}: {pre_request.method} {url} (timeout: {pre_request.timeout_seconds}s)")
            # Convert body to string before slicing (body is a dict, not a string)
            body_str = str(body) if body else "None"
            logger.info(f"Pre-request body: {body_str[:200]}")
            logger.debug(f"Pre-request body: {body}")

            # Make the API call with configured timeout
            timeout = aiohttp.ClientTimeout(total=pre_request.timeout_seconds)

            async with aiohttp_session.request(pre_request.method, url, headers=headers, json=body if body else None, timeout=timeout) as response:
                status_code = response.status

                # Parse response
                try:
                    response_data = await response.json()
                except (ValueError, Exception):
                    response_data = {"text": await response.text()}

                logger.debug(f"Pre-request {pre_request.name} response ({status_code}): {str(response_data)[:200]}")
                logger.info(f"Pre-request {pre_request.name} response ({status_code}): {str(response_data)[:200]}")

                return {"status_code": status_code, "data": response_data, "success": 200 <= status_code < 300}

        except aiohttp.ClientError as e:
            if "timeout" in str(e).lower():
                error_msg = f"Pre-request timed out after {pre_request.timeout_seconds} seconds"
            else:
                error_msg = f"Network error: {e!s}"
            logger.warning(f"Pre-request {pre_request.name} error: {error_msg}")
            return {"status_code": 500, "data": {"error": error_msg}, "success": False}
        except Exception as e:
            error_msg = f"Unexpected error: {e!s}"
            logger.error(f"Pre-request {pre_request.name} error: {error_msg}")
            return {"status_code": 500, "data": {"error": error_msg}, "success": False}

    def _extract_field_from_response(self, response_data: dict | list, json_path: str) -> Any:
        """Extract a field from response using JSONPath.

        Args:
            response_data: Response dictionary or list
            json_path: Path to field (e.g., "sender_id", "data.user.id", "items[0].name")

        Returns:
            Extracted value

        Raises:
            ValueError: If field not found or path invalid
        """
        if not response_data:
            raise ValueError("Response data is empty")

        # Support simple array index: items[0] → items, 0
        import re

        parts = []
        for part in json_path.split("."):
            # Check for array index notation: field[0]
            match = re.match(r"^([^\[]+)\[(\d+)\]$", part)
            if match:
                parts.append(match.group(1))  # field name
                parts.append(int(match.group(2)))  # array index
            else:
                parts.append(part)

        # Navigate through the path
        current = response_data
        path_so_far = []

        for part in parts:
            path_so_far.append(str(part))

            if isinstance(part, int):
                # Array index
                if not isinstance(current, list):
                    raise ValueError(f"Expected list at path '{'.'.join(map(str, path_so_far[:-1]))}', got {type(current).__name__}")

                if part >= len(current):
                    raise ValueError(f"Array index {part} out of range (length: {len(current)}) at path '{'.'.join(map(str, path_so_far[:-1]))}'")

                current = current[part]
            else:
                # Dictionary key
                if not isinstance(current, dict):
                    raise ValueError(f"Expected dict at path '{'.'.join(path_so_far[:-1])}', got {type(current).__name__}")

                if part not in current:
                    available_keys = ", ".join(current.keys()) if isinstance(current, dict) else "N/A"
                    raise ValueError(f"Key '{part}' not found in response at path '{'.'.join(path_so_far[:-1])}'. Available keys: {available_keys}")

                current = current[part]

        if current is None:
            raise ValueError(f"Value at path '{json_path}' is null")

        return current

    async def _process_response(self, result: dict[str, Any], api_config: APIConfig, business_parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Process the API response into a business-friendly result with enhanced error handling."""

        if not result["success"]:
            error_msg = self._get_enhanced_error_message(result["status_code"], result["data"], api_config.error_message)
            return {"success": False, "error": error_msg, "status_code": result["status_code"], "raw_response": result["data"]}

        # Success case
        success_msg = api_config.success_message or "Operation completed successfully"

        # Apply template to success message if it exists
        if success_msg and "{{" in success_msg:
            # Combine business parameters and response data for template substitution
            template_data = {}
            if business_parameters:
                template_data.update(business_parameters)
            if isinstance(result["data"], dict):
                template_data.update(result["data"])
            success_msg = self._apply_message_template(success_msg, template_data)

        return {"success": True, "message": success_msg, "status_code": result["status_code"], "data": result["data"]}

    def _get_enhanced_error_message(self, status_code: int, response_data: dict[str, Any], custom_error_message: str | None) -> str:
        """
        Generate an enhanced error message based on status code and response data.

        Args:
            status_code: HTTP status code
            response_data: Response data from API
            custom_error_message: Custom error message from configuration

        Returns:
            User-friendly error message
        """
        # If custom error message is provided, use it
        if custom_error_message:
            return custom_error_message

        # Standard HTTP status code messages
        status_messages = {
            400: "Invalid request - please check your input parameters",
            401: "Authentication failed - please verify your credentials",
            403: "Permission denied - you don't have access to this resource",
            404: "Resource not found - the requested item doesn't exist",
            409: "Conflict - the resource already exists or cannot be modified",
            422: "Invalid data provided - please check the format of your input",
            429: "Rate limit exceeded - please try again later",
            500: "Server error - the service is temporarily unavailable",
            502: "Service unavailable - the external service is down",
            503: "Service temporarily unavailable - please try again later",
            504: "Request timeout - the service took too long to respond",
        }

        base_message = status_messages.get(status_code, f"API call failed with status {status_code}")

        # Try to extract more specific error information from response
        if isinstance(response_data, dict):
            # Common error fields in API responses
            error_fields = ["error", "message", "detail", "error_description", "errors"]

            for field in error_fields:
                if response_data.get(field):
                    error_detail = response_data[field]
                    if isinstance(error_detail, str):
                        return f"{base_message}: {error_detail}"
                    elif isinstance(error_detail, list) and error_detail:
                        return f"{base_message}: {'; '.join(str(e) for e in error_detail[:3])}"

        return base_message

    def _apply_string_template(self, template: str, parameters: dict[str, Any]) -> str:
        """Apply parameter values to a string template with security sanitization."""
        result = template

        # Replace {{param_name}} with actual values
        for param_name, param_value in parameters.items():
            placeholder = f"{{{{{param_name}}}}}"
            if placeholder in result:
                # Sanitize the parameter value to prevent injection attacks
                sanitized_value = self._sanitize_parameter_value(param_value)
                result = result.replace(placeholder, sanitized_value)

        return result

    def _sanitize_parameter_value(self, value: Any) -> str:
        """
        Sanitize parameter values to prevent injection attacks.

        Args:
            value: The parameter value to sanitize

        Returns:
            Sanitized string value safe for template substitution
        """
        if value is None:
            return ""

        # Convert to string
        str_value = str(value)

        # Remove or escape potentially dangerous characters
        # This prevents JSON injection and other template attacks
        dangerous_chars = {
            '"': '\\"',  # Escape quotes to prevent JSON breaking
            "\\": "\\\\",  # Escape backslashes
            "\n": "\\n",  # Escape newlines
            "\r": "\\r",  # Escape carriage returns
            "\t": "\\t",  # Escape tabs
        }

        sanitized = str_value
        for char, replacement in dangerous_chars.items():
            sanitized = sanitized.replace(char, replacement)

        # Limit length to prevent extremely long values
        max_length = 1000
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."
            logger.warning(f"Parameter value truncated to {max_length} characters")

        return sanitized

    def _apply_message_template(self, template: str, data: dict[str, Any]) -> str:
        """Apply response data to a message template."""
        message = template

        # Replace {{field}} with values from response data
        if isinstance(data, dict):
            for key, value in data.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in message:
                    message = message.replace(placeholder, str(value))

        return message

    async def _validate_and_transform_parameters(self, business_parameters: dict[str, Any], parameter_config: list) -> dict[str, Any]:
        """
        Validate and transform business parameters according to configuration.

        Returns:
            dict with keys: valid (bool), parameters (dict), error (str), details (list)
        """
        validated_params: dict[str, Any] = {}
        validation_errors = []
        warnings = []
        consumed_incoming_keys: set[str] = set()

        # Check required parameters and validate types
        for param_def in parameter_config:
            param_name = param_def.name
            param_type = param_def.type
            is_required = param_def.required
            examples = getattr(param_def, "examples", [])

            # Check if parameter is provided
            if param_name in business_parameters:
                raw_value = business_parameters[param_name]
                consumed_incoming_keys.add(param_name)
            else:
                # Be tolerant to case mismatches (e.g. "phone" vs "Phone") coming from the LLM.
                # Some tools are configured with TitleCase parameter names, while model calls often
                # use lower-case keys. Map case-insensitively when it's unambiguous.
                param_name_lc = str(param_name).lower()
                incoming_key = next(
                    (k for k in business_parameters.keys() if str(k).lower() == param_name_lc),
                    None,
                )
                if incoming_key is not None:
                    raw_value = business_parameters[incoming_key]
                    consumed_incoming_keys.add(incoming_key)
                    if incoming_key != param_name:
                        warnings.append(f"Normalized parameter '{incoming_key}' to '{param_name}'")
                else:
                    raw_value = None

            if raw_value is not None:
                try:
                    # Validate and transform the value
                    validated_value = await self._validate_parameter_value(raw_value, param_type, param_name, examples)
                    validated_params[param_name] = validated_value

                except ValueError as e:
                    validation_errors.append(f"Parameter '{param_name}': {e!s}")

            elif is_required:
                validation_errors.append(f"Required parameter '{param_name}' is missing")
            else:
                # Optional parameter not provided - that's fine
                logger.debug(f"Optional parameter '{param_name}' not provided")

        # Add any extra parameters (not in config) with warning
        for param_name, value in business_parameters.items():
            if param_name in consumed_incoming_keys:
                continue
            if param_name not in validated_params and param_name not in [p.name for p in parameter_config]:
                validated_params[param_name] = value
                warnings.append(f"Unexpected parameter '{param_name}' provided")

        if validation_errors:
            return {"valid": False, "error": f"Parameter validation failed: {'; '.join(validation_errors)}", "details": validation_errors, "warnings": warnings}

        result = {"valid": True, "parameters": validated_params}

        if warnings:
            result["warnings"] = warnings
            logger.warning(f"Parameter validation warnings: {warnings}")

        return result

    async def _validate_parameter_value(self, value: Any, field_type: FieldType, param_name: str, examples: list | None = None) -> Any:
        """
        Validate and transform a single parameter value.

        Args:
            value: The raw value from AI
            field_type: Expected field type
            param_name: Parameter name for error messages
            examples: Example values for reference

        Returns:
            Validated and potentially transformed value

        Raises:
            ValueError: If validation fails
        """
        if value is None:
            raise ValueError("cannot be None")

        try:
            # Use the unified field type utilities for consistent validation
            validation_string = field_type_to_validation_string(field_type)
            validated_value = validate_field_value(validation_string, value)
            return validated_value

        except Exception as e:
            # Provide helpful error message with examples
            error_msg = str(e)
            if examples:
                error_msg += f". Expected format like: {', '.join(examples[:3])}"
            raise ValueError(error_msg)

    async def _apply_basic_transformations(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        Apply basic transformations to parameters for common use cases.

        Args:
            parameters: Validated parameters

        Returns:
            Parameters with basic transformations applied
        """
        transformed_params = parameters.copy()

        for key, value in parameters.items():
            if isinstance(value, str):
                # Transform common date expressions
                if key.endswith("_date") or key.endswith("_time") or "date" in key.lower():
                    transformed_value = self._transform_date_expression(value)
                    if transformed_value != value:
                        transformed_params[key] = transformed_value
                        logger.debug(f"Transformed date parameter '{key}': '{value}' -> '{transformed_value}'")

                # Transform priority/urgency values
                elif key.lower() in ["priority", "urgency", "importance"]:
                    transformed_value = self._transform_priority_value(value)
                    if transformed_value != value:
                        transformed_params[key] = transformed_value
                        logger.debug(f"Transformed priority parameter '{key}': '{value}' -> '{transformed_value}'")

        return transformed_params

    def _transform_date_expression(self, date_str: str) -> str:
        """
        Transform natural language date expressions to ISO format.

        Args:
            date_str: Natural language date like "tomorrow", "next week"

        Returns:
            ISO formatted date string or original if no transformation needed
        """
        date_str_lower = date_str.lower().strip()

        # Simple transformations for common expressions
        today = datetime.now()

        if date_str_lower in ["today", "now"]:
            return today.isoformat()
        elif date_str_lower == "tomorrow":
            from datetime import timedelta

            tomorrow = today + timedelta(days=1)
            return tomorrow.isoformat()
        elif date_str_lower == "yesterday":
            from datetime import timedelta

            yesterday = today - timedelta(days=1)
            return yesterday.isoformat()
        elif "next week" in date_str_lower:
            from datetime import timedelta

            next_week = today + timedelta(weeks=1)
            return next_week.isoformat()

        # Try to parse ISO date format
        try:
            parsed_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return parsed_date.isoformat()
        except (ValueError, TypeError):  # Date parsing errors
            pass

        # Return original if no transformation possible
        return date_str

    def _transform_priority_value(self, priority_str: str) -> str:
        """
        Transform natural language priority to standardized values.

        Args:
            priority_str: Natural language priority like "very urgent", "not important"

        Returns:
            Standardized priority value or original if no transformation needed
        """
        priority_lower = priority_str.lower().strip()

        # Map common priority expressions to standard values
        priority_mapping = {
            # High priority
            "urgent": "high",
            "very urgent": "high",
            "critical": "high",
            "asap": "high",
            "emergency": "high",
            "important": "high",
            # Medium priority
            "normal": "medium",
            "regular": "medium",
            "standard": "medium",
            "moderate": "medium",
            # Low priority
            "low": "low",
            "not urgent": "low",
            "when possible": "low",
            "not important": "low",
            "minor": "low",
        }

        return priority_mapping.get(priority_lower, priority_str)

    async def _get_enhanced_engaging_words(self, tool_config: BusinessTool, business_parameters: dict[str, Any], original_engaging_words: str) -> str:
        """
        Get enhanced engaging words using AI service.

        Args:
            tool_config: Business tool configuration
            business_parameters: Current parameters
            original_engaging_words: Original static engaging words

        Returns:
            Enhanced engaging words string
        """
        try:
            # Validate original engaging words first
            if not validate_engaging_words(original_engaging_words):
                logger.warning(f"Original engaging words invalid: {original_engaging_words}")
                # Generate new ones using AI service
                return await self.ai_engaging_service.generate_engaging_words(tool_config, business_parameters, use_ai=True)

            # Try to enhance the existing words with context
            enhanced = await self.ai_engaging_service.generate_engaging_words(tool_config, business_parameters, use_ai=True)

            # If AI generation fails, fall back to original
            if not enhanced or not validate_engaging_words(enhanced):
                logger.debug(f"AI enhancement failed, using original: {original_engaging_words}")
                return original_engaging_words

            return enhanced

        except Exception as e:
            logger.error(f"Error generating enhanced engaging words: {e}")
            return original_engaging_words
