"""
Comprehensive field validation framework for enhanced field types.

This module provides validation and normalization for advanced field types
including email, phone numbers, URLs, dates, and datetimes.
"""

import json
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import phonenumbers
from phonenumbers import NumberParseException

from app.core.constants import MAX_EMAIL_LENGTH, MAX_PHONE_DIGITS, MAX_URL_LENGTH, MIN_PHONE_DIGITS


class ValidationError(Exception):
    """Custom exception for field validation errors."""

    pass


def validate_email(email: str) -> str:
    """
    Validate and normalize email address.

    Args:
        email: Email address to validate

    Returns:
        Normalized email address (lowercase)

    Raises:
        ValidationError: If email is invalid
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Email must be a non-empty string")

    email = email.strip().lower()

    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError(f"Email too long (max {MAX_EMAIL_LENGTH} characters)")

    # Basic email regex validation
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        raise ValidationError("Invalid email format")

    return email


def validate_phone_number(value: Any) -> str:
    """
    Validate phone number format.

    Supports various formats including:
    - +1234567890
    - +1 (234) 567-8900
    - (234) 567-8900
    - 234-567-8900
    - 2345678900

    Args:
        value: The value to validate as a phone number

    Returns:
        Normalized phone number string

    Raises:
        ValidationError: If phone number format is invalid
    """
    if not isinstance(value, str):
        raise ValidationError("Phone number must be a string")

    phone = value.strip()

    if not phone:
        raise ValidationError("Phone number cannot be empty")

    # Remove common formatting characters
    cleaned_phone = re.sub(r"[\s\-\(\)\+\.]", "", phone)

    # Check if it contains only digits after cleaning
    if not cleaned_phone.isdigit():
        raise ValidationError(f"Phone number contains invalid characters: {value}")

    # Check length using constants
    if len(cleaned_phone) < MIN_PHONE_DIGITS:
        raise ValidationError(f"Phone number too short (min {MIN_PHONE_DIGITS} digits): {value}")

    if len(cleaned_phone) > MAX_PHONE_DIGITS:
        raise ValidationError(f"Phone number too long (max {MAX_PHONE_DIGITS} digits): {value}")

    # Return in E.164 format if it looks like an international number
    if phone.startswith("+"):
        return f"+{cleaned_phone}"
    if len(cleaned_phone) == 10:  # US domestic format
        return f"+1{cleaned_phone}"
    return f"+{cleaned_phone}"


def normalize_phone_identifier(value: Any) -> Optional[str]:
    """Normalize a phone-like identifier into E.164 format.

    This is a convenience wrapper around `validate_phone_number` that returns
    `None` instead of raising when the input is missing/invalid.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return validate_phone_number(candidate)
    except ValidationError:
        return None


def validate_url(url: str) -> str:
    """
    Validate and normalize URL.

    Args:
        url: URL to validate

    Returns:
        Normalized URL

    Raises:
        ValidationError: If URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL must be a non-empty string")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise ValidationError(f"URL too long (max {MAX_URL_LENGTH} characters)")

    try:
        parsed = urlparse(url)

        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError("URL must include scheme (http/https) and domain")

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            raise ValidationError("URL must use http or https scheme")

        return url

    except Exception as e:
        raise ValidationError(f"Invalid URL format: {e}")


def validate_date(date_str: str) -> str:
    """
    Validate and normalize date to YYYY-MM-DD format.

    Args:
        date_str: Date string to validate

    Returns:
        Normalized date string in YYYY-MM-DD format

    Raises:
        ValidationError: If date is invalid
    """
    if not date_str or not isinstance(date_str, str):
        raise ValidationError("Date must be a non-empty string")

    date_str = date_str.strip()

    # Try multiple date formats
    date_formats = [
        "%Y-%m-%d",  # 2023-12-25
        "%m/%d/%Y",  # 12/25/2023
        "%d/%m/%Y",  # 25/12/2023
        "%Y/%m/%d",  # 2023/12/25
        "%m-%d-%Y",  # 12-25-2023
        "%d-%m-%Y",  # 25-12-2023
    ]

    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise ValidationError("Invalid date format. Expected formats: YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY")


def validate_datetime(datetime_str: str) -> str:
    """
    Validate and normalize datetime to ISO 8601 format.

    Args:
        datetime_str: Datetime string to validate

    Returns:
        Normalized datetime string in ISO 8601 format
    Raises:
        ValidationError: If datetime is invalid
    """
    if not datetime_str or not isinstance(datetime_str, str):
        raise ValidationError("Datetime must be a non-empty string")

    datetime_str = datetime_str.strip()

    # Try multiple datetime formats
    datetime_formats = [
        "%Y-%m-%dT%H:%M:%S",  # 2023-12-25T14:30:00
        "%Y-%m-%dT%H:%M:%SZ",  # 2023-12-25T14:30:00Z
        "%Y-%m-%d %H:%M:%S",  # 2023-12-25 14:30:00
        "%m/%d/%Y %H:%M:%S",  # 12/25/2023 14:30:00
        "%d/%m/%Y %H:%M:%S",  # 25/12/2023 14:30:00
        "%Y-%m-%dT%H:%M:%S.%f",  # 2023-12-25T14:30:00.123456
        "%Y-%m-%dT%H:%M:%S.%fZ",  # 2023-12-25T14:30:00.123456Z
    ]

    for fmt in datetime_formats:
        try:
            parsed_datetime = datetime.strptime(datetime_str, fmt)
            return parsed_datetime.isoformat()
        except ValueError:
            continue

    raise ValidationError("Invalid datetime format. Expected ISO 8601 format: YYYY-MM-DDTHH:MM:SS")


def validate_field_value(field_type: str, value: Any) -> Any:
    """
    Validate and normalize a field value based on its type.
    Args:
        field_type: The field type (string, integer, boolean, array, email, phone_number, url, date, datetime)
        value: The value to validate
    Returns:
        Validated and normalized value
    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        raise ValidationError("Value cannot be None")

    # Handle basic types first
    if field_type == "string":
        return str(value).strip()
    elif field_type == "integer":
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid integer value: {value}")
    elif field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ("true", "1", "yes", "on"):
                return True
            elif lower_val in ("false", "0", "no", "off"):
                return False
        raise ValidationError(f"Invalid boolean value: {value}")
    elif field_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            # Try to parse as JSON array first
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            # Fall back to comma-separated values
            return [item.strip() for item in value.split(",") if item.strip()]
        raise ValidationError(f"Invalid array value: {value}")

    # Handle specialized types
    # Convert to string for specialized validation
    str_value = str(value).strip()

    if field_type == "email":
        return validate_email(str_value)
    elif field_type == "phone_number":
        return validate_phone_number(str_value)
    elif field_type == "url":
        return validate_url(str_value)
    elif field_type == "date":
        return validate_date(str_value)
    elif field_type == "datetime":
        return validate_datetime(str_value)
    else:
        raise ValidationError(f"Unknown field type: {field_type}")


def get_field_type_description(field_type: str) -> str:
    """Get description for a field type."""
    descriptions = {
        "string": "Text string value",
        "integer": "Whole number value",
        "boolean": "True or false value",
        "array": "List of values",
        "email": "Valid email address (automatically normalized to lowercase)",
        "phone_number": "Phone number (automatically normalized to E.164 format)",
        "url": "Valid URL with http/https scheme",
        "date": "Date in various formats (normalized to YYYY-MM-DD)",
        "datetime": "Datetime in various formats (normalized to ISO 8601)",
    }
    return descriptions.get(field_type, "Unknown field type")


def get_field_type_examples(field_type: str) -> list[str]:
    """Get example values for a field type."""
    examples = {
        "string": ["Hello World", "Sample text", "Any string value"],
        "integer": ["42", "100", "0"],
        "boolean": ["true", "false"],
        "array": ['["item1", "item2"]', "[1, 2, 3]"],
        "email": ["user@example.com", "john.doe@company.org", "test@domain.co.uk"],
        "phone_number": ["+1234567890", "(555) 123-4567", "+44 20 7946 0958"],
        "url": ["https://example.com", "http://api.service.com/endpoint", "https://www.company.org/path"],
        "date": ["2023-12-25", "12/25/2023", "25/12/2023"],
        "datetime": ["2023-12-25T14:30:00", "2023-12-25 14:30:00", "12/25/2023 14:30:00"],
    }
    return examples.get(field_type, [])
