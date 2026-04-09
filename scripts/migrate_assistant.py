#!/usr/bin/env python3
"""
Migration script to convert old MongoDB assistant document format to new API format.

This script converts assistant configurations from the old MongoDB document format
to the new API format expected by the assistant validation endpoint.

Usage:
    python scripts/migrate_assistant.py < input.json > output.json
    python scripts/migrate_assistant.py --input input.json --output output.json
"""

import argparse
import json
import sys
from typing import Any


def drop_mongodb_metadata(old_config: dict[str, Any]) -> dict[str, Any]:
    """Remove MongoDB-specific metadata fields."""
    fields_to_drop = [
        "_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "agent_type",
        "cost_region",
        "include_cost_estimates",
        "preferred_currency",
        "system_prompt_override",
        "language",
        "language_configs",
    ]
    
    new_config = {k: v for k, v in old_config.items() if k not in fields_to_drop}
    return new_config


def migrate_stt_config(stt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Migrate STT configuration from old format to new format."""
    if not stt:
        return stt
    
    new_stt = stt.copy()
    
    # Extract prompt from advanced_options if it exists
    if "advanced_options" in new_stt and isinstance(new_stt["advanced_options"], dict):
        advanced_options = new_stt["advanced_options"]
        if "prompt" in advanced_options:
            new_stt["prompt"] = advanced_options["prompt"]
        # Drop advanced_options as it's not in the new schema
        del new_stt["advanced_options"]
    
    return new_stt


def migrate_koala_filter(koala_filter: dict[str, Any] | None) -> dict[str, Any] | None:
    """Migrate koala_filter to krisp_viva_filter."""
    if not koala_filter:
        return None
    
    # Map koala_filter to krisp_viva_filter
    krisp_filter = {
        "enabled": koala_filter.get("enabled", True),
    }
    
    # Map noise_suppression_level if it exists
    if "noise_suppression_level" in koala_filter:
        krisp_filter["noise_suppression_level"] = koala_filter["noise_suppression_level"]
    
    return krisp_filter


def migrate_summarization(summarization: dict[str, Any] | None) -> dict[str, Any] | None:
    """Migrate summarization config, dropping fields that are not in schema."""
    if not summarization:
        return summarization
    
    new_summarization = summarization.copy()
    
    # Drop 'fields' as it's not in the new schema
    if "fields" in new_summarization:
        del new_summarization["fields"]
    
    return new_summarization


def migrate_tools(tools: dict[str, Any] | None) -> dict[str, Any] | None:
    """Migrate tools configuration."""
    if not tools:
        return tools
    
    new_tools = tools.copy()
    
    # Rename business_tools to business_tools (structure stays the same)
    # The structure is already correct: array of {tool_id, enabled}
    # No changes needed for business_tools
    
    return new_tools


def migrate_assistant_config(old_config: dict[str, Any]) -> dict[str, Any]:
    """Migrate assistant configuration from old MongoDB format to new API format."""
    # Start by dropping MongoDB metadata
    new_config = drop_mongodb_metadata(old_config)
    
    # Migrate STT config
    if "stt" in new_config:
        new_config["stt"] = migrate_stt_config(new_config["stt"])
    
    # Migrate koala_filter to krisp_viva_filter
    if "koala_filter" in new_config:
        krisp_filter = migrate_koala_filter(new_config["koala_filter"])
        if krisp_filter:
            new_config["krisp_viva_filter"] = krisp_filter
        del new_config["koala_filter"]
    
    # Migrate summarization
    if "summarization" in new_config:
        new_config["summarization"] = migrate_summarization(new_config["summarization"])
    
    # Migrate tools
    if "tools" in new_config:
        new_config["tools"] = migrate_tools(new_config["tools"])
    
    return new_config


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate assistant configuration from old MongoDB format to new API format"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input JSON file (if not provided, reads from stdin)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file (if not provided, writes to stdout)",
    )
    
    args = parser.parse_args()
    
    # Read input
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            old_config = json.load(f)
    else:
        old_config = json.load(sys.stdin)
    
    # Migrate
    try:
        new_config = migrate_assistant_config(old_config)
    except Exception as e:
        print(f"Error during migration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
    else:
        json.dump(new_config, sys.stdout, indent=2, ensure_ascii=False)
        print()  # Add newline at end


if __name__ == "__main__":
    main()
    # Run the script with the following command:
    # python scripts/migrate_assistant.py --input assistant_config.json --output assistant_config_new.json
