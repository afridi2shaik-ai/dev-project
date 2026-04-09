"""
Field Type Utilities

This module provides standardized field type handling utilities to ensure
consistent FieldType enum usage across all validation and registration systems.
"""

from typing import Any

from loguru import logger

from app.schemas.core.business_tool_schema import FieldType


def normalize_field_type(field_type: Any) -> FieldType:
    """
    Normalize a field type to a FieldType enum, handling various input formats.

    Args:
        field_type: Field type as string, FieldType enum, or other format

    Returns:
        Normalized FieldType enum

    Raises:
        ValueError: If field type cannot be normalized
    """
    if isinstance(field_type, FieldType):
        return field_type

    if isinstance(field_type, str):
        # Handle string field types
        field_type = field_type.lower().strip()

        # Map common string variations to FieldType enums
        string_to_enum = {
            "string": FieldType.STRING,
            "str": FieldType.STRING,
            "text": FieldType.STRING,
            "integer": FieldType.INTEGER,
            "int": FieldType.INTEGER,
            "number": FieldType.INTEGER,
            "boolean": FieldType.BOOLEAN,
            "bool": FieldType.BOOLEAN,
            "array": FieldType.ARRAY,
            "list": FieldType.ARRAY,
            "email": FieldType.EMAIL,
            "phone_number": FieldType.PHONE_NUMBER,
            "phone": FieldType.PHONE_NUMBER,
            "url": FieldType.URL,
            "uri": FieldType.URL,
            "date": FieldType.DATE,
            "datetime": FieldType.DATETIME,
            "timestamp": FieldType.DATETIME,
        }

        if field_type in string_to_enum:
            return string_to_enum[field_type]

        # Try to match FieldType enum values directly
        try:
            return FieldType(field_type)
        except ValueError:
            pass

    # Default to STRING for unknown types with warning
    logger.warning(f"Unknown field type '{field_type}', defaulting to STRING")
    return FieldType.STRING


def field_type_to_json_schema_type(field_type: FieldType) -> str:
    """
    Convert a FieldType enum to JSON Schema type string.

    Args:
        field_type: FieldType enum value

    Returns:
        JSON Schema type string
    """
    type_mapping = {
        FieldType.STRING: "string",
        FieldType.INTEGER: "integer",
        FieldType.BOOLEAN: "boolean",
        FieldType.ARRAY: "array",
        # Advanced types are still strings but with validation
        FieldType.EMAIL: "string",
        FieldType.PHONE_NUMBER: "string",
        FieldType.URL: "string",
        FieldType.DATE: "string",
        FieldType.DATETIME: "string",
    }

    return type_mapping.get(field_type, "string")


def field_type_to_validation_string(field_type: FieldType) -> str:
    """
    Convert a FieldType enum to the string format expected by field validators.

    Args:
        field_type: FieldType enum value

    Returns:
        Field type string for validation
    """
    return field_type.value


def get_field_type_json_schema_properties(field_type: FieldType) -> dict[str, Any]:
    """
    Get additional JSON Schema properties for a field type.

    Args:
        field_type: FieldType enum value

    Returns:
        Dictionary of additional JSON Schema properties
    """
    properties = {}

    if field_type == FieldType.EMAIL:
        properties["format"] = "email"
    elif field_type == FieldType.URL:
        properties["format"] = "uri"
    elif field_type == FieldType.DATE:
        properties["format"] = "date"
    elif field_type == FieldType.DATETIME:
        properties["format"] = "date-time"
    elif field_type == FieldType.PHONE_NUMBER:
        properties["pattern"] = r"^\+[1-9]\d{1,14}$"
    elif field_type == FieldType.ARRAY:
        properties["items"] = {"type": "string"}

    return properties


def create_json_schema_property(field_type: FieldType, description: str = "", examples: list[str] | None = None) -> dict[str, Any]:
    """
    Create a complete JSON Schema property for a field type.

    Args:
        field_type: FieldType enum value
        description: Field description
        examples: List of example values

    Returns:
        Complete JSON Schema property dictionary
    """
    # Start with basic schema
    schema = {
        "type": field_type_to_json_schema_type(field_type),
        "description": description,
    }

    # Add additional properties for special types
    additional_props = get_field_type_json_schema_properties(field_type)
    schema.update(additional_props)

    # Add examples if provided
    if examples:
        schema["examples"] = examples

    return schema


def validate_field_type_compatibility(source_type: Any, target_type: Any) -> bool:
    """
    Check if two field types are compatible for validation purposes.

    Args:
        source_type: Source field type (any format)
        target_type: Target field type (any format)

    Returns:
        True if types are compatible, False otherwise
    """
    try:
        normalized_source = normalize_field_type(source_type)
        normalized_target = normalize_field_type(target_type)
        return normalized_source == normalized_target
    except (ValueError, TypeError):
        return False
