"""
Centralized configuration for engaging_words parameter across all custom API tools.

This module provides a single source of truth for engaging_words parameter
definition, description, validation, and utility functions to avoid duplication
across the entire application.

Usage:
    from app.tools.engaging_words_config import (
        get_engaging_words_schema,
        get_engaging_words_docstring,
        validate_engaging_words,
        get_default_engaging_words,
        get_random_engaging_words,
        ENGAGING_WORDS_PARAM_CONFIG
    )
"""

import random
from typing import Any

# Local constants to avoid circular imports
DEFAULT_ENGAGING_WORDS = "Processing your request..."
MAX_ENGAGING_WORDS_LENGTH = 100

# Centralized engaging_words parameter configuration
ENGAGING_WORDS_PARAM_CONFIG = {
    "name": "engaging_words",
    "type": "string",
    "required": True,
    "description": ("REQUIRED: Brief phrase describing the ACTION being performed during API call. NEVER repeat the user's question. Use action verbs like: 'Fetching your assistant information...', 'Retrieving system data...', 'Looking up configurations...', 'Getting details from the API...', 'Searching the database...'. Keep it short and action-focused."),
    "examples": ["Fetching your assistant information...", "Retrieving system data...", "Looking up configurations...", "Getting details from the API...", "Searching the database...", DEFAULT_ENGAGING_WORDS, "Updating the records...", "Saving the information..."],
}


def get_engaging_words_schema() -> dict[str, Any]:
    """Get the JSON schema definition for engaging_words parameter."""
    return {"type": ENGAGING_WORDS_PARAM_CONFIG["type"], "description": ENGAGING_WORDS_PARAM_CONFIG["description"]}


def get_engaging_words_docstring() -> str:
    """Get the docstring description for engaging_words parameter."""
    return f"engaging_words: {ENGAGING_WORDS_PARAM_CONFIG['description']}"


def validate_engaging_words(engaging_words: str) -> bool:
    """
    Validate engaging_words parameter.

    Args:
        engaging_words: The engaging words to validate

    Returns:
        True if valid, False otherwise
    """
    if not engaging_words or not engaging_words.strip():
        return False

    # Check if it's too long (should be brief)
    if len(engaging_words) > MAX_ENGAGING_WORDS_LENGTH:
        return False

    # Check if it ends with ellipsis (good practice)
    return engaging_words.strip().endswith("...")


def get_default_engaging_words() -> str:
    """Get a default engaging words phrase for testing."""
    return DEFAULT_ENGAGING_WORDS


def get_random_engaging_words() -> str:
    """Get a random engaging words phrase from the examples."""
    return random.choice(ENGAGING_WORDS_PARAM_CONFIG["examples"])


def get_contextual_engaging_words(context: str = "general") -> str:
    """
    Get contextual engaging words based on the operation type.
    Args:
        context: The type of operation ('assistant', 'data', 'config', 'general')

    Returns:
        Appropriate engaging words for the context
    """
    context_map = {"assistant": "Fetching your assistant information...", "data": "Retrieving system data...", "config": "Looking up configurations...", "database": "Searching the database...", "api": "Getting details from the API...", "general": DEFAULT_ENGAGING_WORDS, "update": "Updating the records...", "save": "Saving the information..."}

    return context_map.get(context.lower(), context_map["general"])


def create_custom_engaging_words(action: str, target: str = "") -> str:
    """
    Create custom engaging words based on action and target.

    Args:
        action: The action being performed (e.g., 'fetching', 'retrieving', 'updating')
        target: Optional target of the action (e.g., 'assistant information', 'user data')

    Returns:
        Formatted engaging words string
    """
    if target:
        return f"{action.capitalize()} {target}..."
    else:
        return f"{action.capitalize()} the information..."


def is_valid_engaging_words_format(engaging_words: str) -> bool:
    """
    Check if engaging words follow the expected format.

    Args:
        engaging_words: The engaging words to check

    Returns:
        True if format is valid, False otherwise
    """
    if not engaging_words or not engaging_words.strip():
        return False

    words = engaging_words.strip()

    # Should end with ellipsis
    if not words.endswith("..."):
        return False

    # Should not be too short (at least 10 characters excluding ellipsis)
    if len(words.replace("...", "")) < 10:
        return False

    # Should contain action words (present participle or imperative)
    action_indicators = ["fetching", "retrieving", "getting", "looking", "searching", "processing", "updating", "saving", "loading", "checking"]

    words_lower = words.lower()
    return any(indicator in words_lower for indicator in action_indicators)


def get_all_examples() -> list[str]:
    """Get all available engaging words examples."""
    return ENGAGING_WORDS_PARAM_CONFIG["examples"].copy()


def get_parameter_info() -> dict[str, Any]:
    """Get complete parameter information for function signatures."""
    return {"name": ENGAGING_WORDS_PARAM_CONFIG["name"], "type": ENGAGING_WORDS_PARAM_CONFIG["type"], "required": ENGAGING_WORDS_PARAM_CONFIG["required"], "description": ENGAGING_WORDS_PARAM_CONFIG["description"], "examples": get_all_examples()}


# Export all utility functions for easy importing
__all__ = ["ENGAGING_WORDS_PARAM_CONFIG", "create_custom_engaging_words", "get_all_examples", "get_contextual_engaging_words", "get_default_engaging_words", "get_engaging_words_docstring", "get_engaging_words_schema", "get_parameter_info", "get_random_engaging_words", "is_valid_engaging_words_format", "validate_engaging_words"]
