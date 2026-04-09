"""
Configuration Merging Utilities

This module provides standardized configuration merging utilities to ensure
consistent behavior when merging agent configurations across the system.
"""

from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.schemas import AgentConfig


def format_config_strings(config_obj: Any, format_vars: dict[str, Any]) -> Any:
    """Recursively formats string values in a configuration object (like Pydantic models or dicts)
    using a dictionary of variables.
    """
    if isinstance(config_obj, dict):
        return {k: format_config_strings(v, format_vars) for k, v in config_obj.items()}
    if isinstance(config_obj, list):
        return [format_config_strings(i, format_vars) for i in config_obj]
    if isinstance(config_obj, str):
        try:
            return config_obj.format(**format_vars)
        except KeyError:
            # Ignore strings that don't have matching format variables
            return config_obj
    else:
        # Return non-string, non-collection types as is
        return config_obj


def cleanup_discriminated_unions(config_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Clean up invalid fields from discriminated unions in config data.
    
    This removes fields that don't belong to the current variant, preventing
    validation errors when parsing configs from external sources (e.g., assistant API)
    that may contain invalid field combinations.
    
    Args:
        config_dict: Configuration dictionary to clean
        
    Returns:
        Cleaned configuration dictionary
    """
    # Field mappings for first_message variants
    FIRST_MESSAGE_VARIANT_FIELDS = {
        "speak_first": {"text"},
        "wait_for_user": set(),
        "model_generated": {"prompt"},
    }
    
    # Clean up first_message if present
    if "first_message" in config_dict and isinstance(config_dict["first_message"], dict):
        first_msg = config_dict["first_message"]
        mode = first_msg.get("mode")
        
        if mode in FIRST_MESSAGE_VARIANT_FIELDS:
            # Get allowed fields for this variant
            allowed_fields = FIRST_MESSAGE_VARIANT_FIELDS[mode] | {"mode"}
            # Remove any fields that don't belong to this variant
            cleaned_first_msg = {k: v for k, v in first_msg.items() if k in allowed_fields}
            config_dict["first_message"] = cleaned_first_msg
            logger.debug(f"Cleaned first_message: removed invalid fields, kept: {list(cleaned_first_msg.keys())}")
    
    return config_dict


def deep_merge_dicts(base_dict: dict, update_dict: dict) -> dict:
    """Recursively merges update_dict into base_dict.
    
    Special handling for discriminated unions:
    - If the discriminator field changes, replace the entire object
    - This prevents invalid field combinations when switching between union variants
    
    Special merge behaviors:
    - None values: Explicitly clear the field (overwrite base)
    - Empty dict {}: Replace base dict with empty dict (explicit clear)
    - Empty list []: Replace base list with empty list (explicit clear)
    - Lists: Always replaced, not merged element-by-element
    
    Discriminated unions handled:
    - first_message: discriminator "mode"
    - stt, tts, llm: discriminator "provider"
    - summarization: discriminator "provider"
    - processors.filler_words, processors.idle_timeout: discriminator "provider"
    - background_audio.config: discriminator "type"
    """
    # Discriminator fields for known discriminated unions
    DISCRIMINATOR_FIELDS = {
        "first_message": "mode",
        "stt": "provider",
        "tts": "provider",
        "llm": "provider",
        "summarization": "provider",
        "filler_words": "provider",
        "idle_timeout": "provider",
    }
    
    # Fields that should be replaced entirely, never merged recursively
    # These are typically free-form dicts where merging doesn't make semantic sense
    REPLACE_ONLY_FIELDS = {
        "metadata",  # Free-form metadata should be replaced
        "extra",  # customer_details.extra should be replaced
        "params",  # TTS/STT params should be replaced as a unit
    }
    
    for key, value in update_dict.items():
        # Handle nested discriminated unions (e.g., processors.filler_words)
        if key == "processors" and isinstance(value, dict) and isinstance(base_dict.get(key), dict):
            # Check filler_words and idle_timeout discriminators
            for sub_key in ["filler_words", "idle_timeout"]:
                if sub_key in value and isinstance(value[sub_key], dict) and isinstance(base_dict[key].get(sub_key), dict):
                    update_provider = value[sub_key].get("provider")
                    base_provider = base_dict[key][sub_key].get("provider")
                    if update_provider and update_provider != base_provider:
                        # Discriminator changed - replace entire object
                        base_dict[key][sub_key] = value[sub_key]
                        continue
        
        # Handle background_audio.config discriminated union
        if key == "background_audio" and isinstance(value, dict) and isinstance(base_dict.get(key), dict):
            if "config" in value and isinstance(value["config"], dict) and isinstance(base_dict[key].get("config"), dict):
                update_type = value["config"].get("type")
                base_type = base_dict[key]["config"].get("type")
                if update_type and update_type != base_type:
                    # Discriminator changed - replace entire config object
                    base_dict[key]["config"] = value["config"]
                    continue
        
        # Handle top-level discriminated unions
        if key in DISCRIMINATOR_FIELDS and isinstance(value, dict) and isinstance(base_dict.get(key), dict):
            discriminator_field = DISCRIMINATOR_FIELDS[key]
            update_discriminator = value.get(discriminator_field)
            base_discriminator = base_dict[key].get(discriminator_field)
            
            if update_discriminator and update_discriminator != base_discriminator:
                # Discriminator changed - replace entire object to avoid invalid field combinations
                base_dict[key] = value
                logger.debug(f"🔄 Discriminator changed for '{key}': {base_discriminator} → {update_discriminator} (replaced entire object)")
                continue
        
        # Handle fields that should be replaced entirely (free-form dicts)
        if key in REPLACE_ONLY_FIELDS and isinstance(value, dict):
            base_dict[key] = value
            logger.debug(f"🔄 Replaced entire '{key}' (replace-only field)")
            continue
        
        # Handle explicit clears: empty dict means "clear this nested config"
        if isinstance(value, dict) and len(value) == 0:
            base_dict[key] = {}
            logger.debug(f"🗑️ Cleared '{key}' with empty dict")
            continue
        
        # Handle explicit clears: empty list means "clear this list"
        if isinstance(value, list) and len(value) == 0:
            base_dict[key] = []
            logger.debug(f"🗑️ Cleared '{key}' with empty list")
            continue
        
        # Handle None values: explicit clear/unset
        # CHANGED: None now explicitly clears the field instead of preserving base
        if value is None:
            base_dict[key] = None
            logger.debug(f"🗑️ Set '{key}' to None (explicit clear)")
            continue
        
        # If the update value is a dict, and the base also has that key as a dict, recurse.
        # This handles nested structures like language_configs["en"].stt, etc.
        if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
            base_dict[key] = deep_merge_dicts(base_dict[key], value)
        # Lists are always replaced entirely, not merged element-by-element
        # This is standard behavior for configuration merging
        elif isinstance(value, list):
            base_dict[key] = value
            logger.debug(f"🔄 Replaced list '{key}' (lists are always replaced, not merged)")
        else:
            # Simple value assignment (strings, numbers, bools, etc.)
            base_dict[key] = value
    
    return base_dict


def merge_configs(base_config: AgentConfig, override_data: dict[str, Any] | None = None) -> AgentConfig:
    """Merges an override dict into a base config and validates the result.
    
    Merge order:
    1. Start with base config
    2. Apply language-specific config (if language is set)
    3. Apply session overrides
    4. Validate final config
    
    Args:
        base_config: Base AgentConfig from assistant definition
        override_data: Optional session-level overrides
        
    Returns:
        Merged and validated AgentConfig
        
    Raises:
        ValueError: If merged config fails validation
    """
    # 1. Start with base config dictionary.
    base_dict = base_config.model_dump()
    logger.debug(f"🔧 Starting config merge - base has {len(base_dict)} top-level keys")

    # 2. Determine the final language by checking the override first, then the base.
    final_language = (override_data.get("language") if override_data else None) or base_dict.get("language")
    
    if final_language:
        logger.debug(f"🌐 Target language: {final_language}")

    # 3. Create the baseline by merging language-specific settings from the base config.
    if final_language:
        language_configs = base_dict.get("language_configs", {})
        if final_language in language_configs:
            language_specific_config = language_configs[final_language]

            language_specific_dict = {}
            if hasattr(language_specific_config, "model_dump"):
                language_specific_dict = language_specific_config.model_dump(exclude_unset=True)
            elif isinstance(language_specific_config, dict):
                language_specific_dict = language_specific_config

            # Merge the language settings into the base to create a new baseline.
            logger.debug(f"🌐 Merging language-specific config for '{final_language}' ({len(language_specific_dict)} overrides)")
            base_dict = deep_merge_dicts(base_dict, language_specific_dict)
        else:
            logger.debug(f"⚠️ Language '{final_language}' not found in language_configs")

    # 4. If there are overrides, merge them into the baseline.
    if override_data:
        logger.debug(f"🔄 Applying session overrides ({len(override_data)} top-level keys)")
        base_dict = deep_merge_dicts(base_dict, override_data)
    else:
        logger.debug("✓ No session overrides to apply")

    # 5. Re-validate the merged dictionary into an AgentConfig object.
    try:
        final_config = AgentConfig(**base_dict)
        logger.debug("✅ Config merge completed and validated successfully")
        return final_config
    except ValidationError as e:
        logger.error(f"❌ Config validation failed after merge: {e}")
        # Log specific validation errors for debugging
        for error in e.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            logger.error(f"  - {field_path}: {error['msg']} (type: {error['type']})")
        raise ValueError(f"Invalid merged configuration: {e}")


def merge_agent_configs_pydantic(base_config: AgentConfig, override_config: AgentConfig | None = None) -> AgentConfig:
    """
    Merge two AgentConfig objects using standardized deep merge logic.

    Args:
        base_config: Base AgentConfig to merge into
        override_config: AgentConfig with override values

    Returns:
        Merged AgentConfig instance

    Raises:
        ValueError: If merged configuration is invalid
    """
    if not override_config:
        logger.debug("No override config provided, returning base config")
        return base_config

    # Convert override config to dict and use the dict-based merge
    override_data = override_config.model_dump(exclude_unset=True)
    return merge_configs(base_config, override_data)


def validate_config_merge_compatibility(base_config: AgentConfig, override_data: dict[str, Any]) -> list[str]:
    """
    Validate that override data is compatible with base config before merging.

    Args:
        base_config: Base AgentConfig
        override_data: Dictionary of override data

    Returns:
        List of validation warnings (empty if all good)
    """
    warnings = []

    try:
        # Attempt the merge to check for validation issues
        merge_configs(base_config, override_data)
    except ValueError as e:
        warnings.append(f"Config merge validation failed: {e}")

    # Check for potentially problematic overrides
    base_dict = base_config.model_dump()

    for key, value in override_data.items():
        if key not in base_dict:
            warnings.append(f"Override key '{key}' not found in base config")
        elif isinstance(base_dict[key], dict) and not isinstance(value, dict):
            warnings.append(f"Override for '{key}' replaces nested config with simple value")

    return warnings


def create_config_override_summary(base_config: AgentConfig, override_data: dict[str, Any]) -> dict[str, Any]:
    """
    Create a summary of what will be overridden in a config merge.

    Args:
        base_config: Base AgentConfig
        override_data: Dictionary of override data

    Returns:
        Summary dictionary with override details
    """
    summary = {
        "total_overrides": len(override_data),
        "override_keys": list(override_data.keys()),
        "base_config_keys": len(base_config.model_dump()),
        "nested_overrides": [],
        "new_keys": [],
        "replaced_keys": [],
    }

    base_dict = base_config.model_dump()

    for key, value in override_data.items():
        if key not in base_dict:
            summary["new_keys"].append(key)
        elif isinstance(base_dict[key], dict) and isinstance(value, dict):
            summary["nested_overrides"].append(key)
        else:
            summary["replaced_keys"].append(key)

    return summary


def log_config_merge_details(base_config: AgentConfig, override_data: dict[str, Any]) -> None:
    """
    Log detailed information about a config merge operation.

    Args:
        base_config: Base AgentConfig
        override_data: Dictionary of override data
    """
    if not override_data:
        logger.debug("No config merge needed - no overrides provided")
        return

    summary = create_config_override_summary(base_config, override_data)

    logger.info(f"🔧 Config merge: {summary['total_overrides']} overrides on {summary['base_config_keys']} base keys")

    if summary["new_keys"]:
        logger.debug(f"  New keys: {summary['new_keys']}")

    if summary["replaced_keys"]:
        logger.debug(f"  Replaced keys: {summary['replaced_keys']}")

    if summary["nested_overrides"]:
        logger.debug(f"  Nested overrides: {summary['nested_overrides']}")

    # Check for warnings
    warnings = validate_config_merge_compatibility(base_config, override_data)
    if warnings:
        for warning in warnings:
            logger.warning(f"⚠️ Config merge warning: {warning}")


# Backward compatibility alias
merge_agent_configs = merge_configs
