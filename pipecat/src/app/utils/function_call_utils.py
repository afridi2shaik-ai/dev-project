"""
Function Call Parameter Utilities

This module provides standardized parameter extraction and handling utilities
for all function call implementations to ensure consistency across the system.
"""

from typing import Any

from loguru import logger


def extract_function_parameters(kwargs: dict[str, Any], expected_params: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Extract function parameters from kwargs in a standardized way.

    Handles both direct and nested parameter formats consistently:
    - Direct format: function(param1="value1", param2="value2")
    - Nested format: function(kwargs={"param1": "value1", "param2": "value2"})

    Args:
        kwargs: Raw kwargs from function call
        expected_params: List of expected parameter names (optional)

    Returns:
        Tuple of (function_parameters, metadata_parameters)
        - function_parameters: The actual business/tool parameters
        - metadata_parameters: Special parameters like engaging_words, etc.
    """
    function_parameters = {}
    metadata_parameters = {}

    # Special metadata parameter names that should be extracted separately
    metadata_param_names = {"engaging_words", "reason", "timeout", "retry_count"}

    try:
        # Check for nested kwargs format first
        if "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
            logger.debug("Using nested kwargs format for parameter extraction")
            # Extract nested parameters
            nested_kwargs = kwargs["kwargs"].copy()

            # Separate metadata from function parameters
            for key, value in nested_kwargs.items():
                if key in metadata_param_names:
                    metadata_parameters[key] = value
                else:
                    function_parameters[key] = value

            # Extract any top-level metadata parameters
            for key, value in kwargs.items():
                if key != "kwargs" and key in metadata_param_names:
                    metadata_parameters[key] = value

        else:
            # Direct format - separate metadata from function parameters
            logger.debug("Using direct format for parameter extraction")
            for key, value in kwargs.items():
                if key in metadata_param_names:
                    metadata_parameters[key] = value
                else:
                    function_parameters[key] = value

    except Exception as e:
        logger.error(f"Error extracting function parameters: {e}")
        # Fallback to treating everything as function parameters
        function_parameters = kwargs.copy()
        metadata_parameters = {}

    logger.debug(f"Extracted function parameters: {list(function_parameters.keys())}")
    logger.debug(f"Extracted metadata parameters: {list(metadata_parameters.keys())}")

    return function_parameters, metadata_parameters


def get_metadata_parameter(metadata: dict[str, Any], param_name: str, default: Any = None) -> Any:
    """
    Get a metadata parameter with a default value.

    Args:
        metadata: Metadata parameters dict
        param_name: Parameter name to retrieve
        default: Default value if parameter not found

    Returns:
        Parameter value or default
    """
    return metadata.get(param_name, default)


def validate_required_parameters(parameters: dict[str, Any], required_params: list[str]) -> list[str]:
    """
    Validate that all required parameters are present.

    Args:
        parameters: Function parameters dict
        required_params: List of required parameter names

    Returns:
        List of missing parameter names (empty if all present)
    """
    missing_params = []

    for param_name in required_params:
        if param_name not in parameters or parameters[param_name] is None:
            missing_params.append(param_name)

    return missing_params


def log_function_call(function_name: str, parameters: dict[str, Any], metadata: dict[str, Any]) -> None:
    """
    Log function call details in a standardized format.

    Args:
        function_name: Name of the function being called
        parameters: Function parameters
        metadata: Metadata parameters
    """
    param_summary = {key: type(value).__name__ for key, value in parameters.items()}
    metadata_summary = {key: type(value).__name__ for key, value in metadata.items()}

    logger.info(f"🔧 Function call: {function_name}")
    logger.debug(f"  Parameters: {param_summary}")
    logger.debug(f"  Metadata: {metadata_summary}")
