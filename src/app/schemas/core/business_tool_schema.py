"""
Simplified Business Tool Schemas

This module defines schemas for the new simplified business tools system that
replaces the legacy custom API tools. Business tools focus on simplicity and
hide technical complexity from the AI.
"""

import datetime
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.base_schema import BaseSchema
from app.schemas.user_schema import UserInfo

# Avoid circular import by defining constant locally
DEFAULT_TIMEOUT_SECONDS = 30.0


class FieldType(str, Enum):
    """Supported field types for business parameters."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    URL = "url"
    DATE = "date"
    DATETIME = "datetime"


class BusinessParameter(BaseSchema):
    """Configuration for a single business parameter that the AI needs to collect."""

    name: str = Field(..., description="The parameter name (business-friendly)")
    type: FieldType = Field(..., description="The expected data type")
    description: str = Field(..., description="Clear description for the AI")
    required: bool = Field(True, description="Whether this parameter is required")
    examples: list[str] | None = Field(None, description="Example values to help the AI")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.replace("_", "").isalnum():
            raise ValueError("Parameter name must be alphanumeric with underscores")
        return v


# Authentication configurations
class AuthenticationConfig(BaseSchema):
    """Base authentication configuration."""

    type: str = Field(..., description="Authentication type")


class BearerAuthConfig(AuthenticationConfig):
    """Bearer token authentication."""

    type: Literal["bearer"] = "bearer"
    token: str = Field(..., description="Bearer token (can use {{ENV_VAR}} syntax)")


class ApiKeyAuthConfig(AuthenticationConfig):
    """API key authentication."""

    type: Literal["api_key"] = "api_key"
    api_key: str = Field(..., description="API key value")
    header_name: str = Field("X-API-Key", description="Header name for the API key")


class BasicAuthConfig(AuthenticationConfig):
    """Basic authentication."""

    type: Literal["basic"] = "basic"
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class OAuth2AuthConfig(AuthenticationConfig):
    """OAuth 2.0 authentication."""

    type: Literal["oauth2"] = "oauth2"
    client_id: str = Field(..., description="OAuth 2.0 client ID")
    client_secret: str = Field(..., description="OAuth 2.0 client secret")
    token_url: str = Field(..., description="Token endpoint URL")
    scope: str | None = Field(None, description="OAuth 2.0 scope")
    grant_type: Literal["client_credentials", "authorization_code"] = Field("client_credentials", description="OAuth 2.0 grant type")


class CustomAuthConfig(AuthenticationConfig):
    """Custom authentication with headers."""

    type: Literal["custom"] = "custom"
    headers: dict[str, str] = Field(..., description="Custom authentication headers")


class CustomTokenDBAuthConfig(AuthenticationConfig):
    """Database-backed custom token authentication with automatic token rotation.

    Supports multi-token authentication where multiple tokens (e.g., access_token + id_token)
    are extracted from a single API response and placed in different HTTP headers.
    """

    type: Literal["custom_token_db"] = "custom_token_db"
    credential_id: str = Field(..., description="ID of the API credential stored in database")


# Union type for all authentication configs
AuthConfig = BearerAuthConfig | ApiKeyAuthConfig | BasicAuthConfig | OAuth2AuthConfig | CustomAuthConfig | CustomTokenDBAuthConfig


class PreRequestCacheConfig(BaseSchema):
    """Cache configuration for pre-request results.
    
    When enabled, pre-request results are cached for the duration of the agent session,
    eliminating redundant API calls for the same data within a conversation.
    """

    enabled: bool = Field(default=False, description="Enable caching for this pre-request during the session")
    cache_key: str | None = Field(default=None, description="Optional custom cache key. If not provided, uses pre-request name as key")


class PreRequestConfig(BaseSchema):
    """Configuration for a pre-request API call that executes before the main call.
    
    Pre-requests allow chaining API calls where data from one response is used in subsequent requests.
    Example use case: Initialize session → Get sender_id → Use in main API call
    """

    name: str = Field(..., description="Identifier for this pre-request (used in field references)")
    description: str = Field(..., description="Description of what this pre-request does")

    # API configuration (relative to main api_config.base_url)
    endpoint: str = Field(..., description="API endpoint path (relative to main base_url)")
    method: str = Field("POST", description="HTTP method")

    # Request configuration
    headers: dict[str, str] | None = Field(None, description="Additional headers for this request")
    body_template: dict[str, Any] | None = Field(None, description="Request body template - use {{param_name}} to insert AI-collected parameters")
    query_params: dict[str, str] | None = Field(None, description="Query parameters - use {{param_name}} to insert AI-collected parameters")

    # Response extraction - extract specific fields from the response
    extract_fields: dict[str, str] = Field(..., description="Fields to extract from response: {new_field_name: response_json_path}")

    # Timeout
    timeout_seconds: float = Field(10.0, ge=1.0, le=60.0, description="Request timeout in seconds")

    # Caching
    cache_config: PreRequestCacheConfig | None = Field(default=None, description="Optional caching configuration. When enabled, results are cached for the session duration")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        if v.upper() not in allowed_methods:
            raise ValueError(f"Method must be one of: {allowed_methods}")
        return v.upper()

    @field_validator("extract_fields")
    @classmethod
    def validate_extract_fields(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("At least one field must be extracted from pre-request response")
        return v


class APIConfig(BaseSchema):
    """Simplified configuration for API calls."""

    base_url: str = Field(..., description="Base URL for the API")
    endpoint: str = Field(..., description="API endpoint path")
    method: str = Field("POST", description="HTTP method")
    timeout_seconds: float = Field(DEFAULT_TIMEOUT_SECONDS, ge=1.0, le=300.0, description="Request timeout in seconds for API calls")

    # Authentication
    authentication: AuthConfig | None = Field(None, description="Authentication configuration")

    # Parameter mapping - AI parameters can be mapped to API call components
    query_params: dict[str, str] = Field(default_factory=dict, description="Query parameters - use {{param_name}} to insert AI-collected parameters, or static values")
    body_template: dict[str, Any] | None = Field(None, description="Request body template - use {{param_name}} to insert AI-collected parameters or {{pre_request.field_name}} for pre-request results")

    # Response handling
    success_message: str | None = Field(None, description="Message to show on success (can use {{field}} from response)")
    error_message: str | None = Field(None, description="Message to show on error")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        if v.upper() not in allowed_methods:
            raise ValueError(f"Method must be one of: {allowed_methods}")
        return v.upper()


class BusinessTool(BaseSchema):
    """Simplified business tool configuration."""

    tool_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id", description="Unique tool identifier")
    tenant_id: str = Field(..., description="Tenant this tool belongs to")

    # Basic information
    name: str = Field(..., description="Tool name (used as function name)")
    description: str = Field(..., description="Description of what this tool does")

    # What AI needs to collect
    parameters: list[BusinessParameter] = Field(default_factory=list, description="Parameters for the AI to collect")

    # Multi-step workflow support
    pre_requests: list[PreRequestConfig] = Field(default_factory=list, description="Pre-requests to execute before main API call (for chained workflows)")

    # API configuration
    api_config: APIConfig = Field(..., description="API call configuration")

    # What to say while processing
    engaging_words: str = Field("Processing your request...", description="What to say while making the API call")

    # Metadata
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC), description="Creation timestamp")
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC), description="Last update timestamp")
    created_by: UserInfo | None = Field(None, description="User who created this tool")
    updated_by: UserInfo | None = Field(None, description="User who last updated this tool")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Auto-convert spaces to underscores for user convenience
        normalized_name = v.strip().replace(" ", "_")

        # Check if the normalized name (without underscores) is alphanumeric
        if not normalized_name.replace("_", "").isalnum():
            raise ValueError("Tool name must contain only letters, numbers, and spaces/underscores")

        return normalized_name


# Request/Response schemas
class BusinessToolCreateRequest(BaseSchema):
    """Simplified request schema for creating a new business tool."""

    name: str = Field(..., description="Tool name (used as function name)")
    description: str = Field(..., description="Description of what this tool does")
    parameters: list[BusinessParameter] = Field(default_factory=list, description="Parameters for the AI to collect")
    pre_requests: list[PreRequestConfig] = Field(default_factory=list, description="Pre-requests to execute before main API call (for chained workflows)")
    api_config: APIConfig = Field(..., description="API call configuration")
    engaging_words: str = Field("Processing your request...", description="What to say while making the API call")


class BusinessToolUpdateRequest(BaseSchema):
    """Simplified request schema for updating an existing business tool."""

    name: str | None = Field(None, description="Tool name (used as function name)")
    description: str | None = Field(None, description="Description of what this tool does")
    parameters: list[BusinessParameter] | None = Field(None, description="Parameters for the AI to collect")
    pre_requests: list[PreRequestConfig] | None = Field(None, description="Pre-requests to execute before main API call (for chained workflows)")
    api_config: APIConfig | None = Field(None, description="API call configuration")
    engaging_words: str | None = Field(None, description="What to say while making the API call")


class BusinessToolListItem(BaseSchema):
    """Simplified business tool information for listing."""

    tool_id: str = Field(..., description="Unique tool identifier", alias="_id")
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Description of what this tool does")
    parameter_count: int = Field(..., description="Number of parameters")
    created_at: datetime.datetime = Field(..., description="Creation timestamp")
    updated_at: datetime.datetime = Field(..., description="Last update timestamp")


class BusinessToolTestRequest(BaseSchema):
    """Request schema for testing a business tool."""

    parameters: dict[str, Any] = Field(..., description="Business parameters to test with")
    engaging_words: str | None = Field(None, description="Engaging words to use during test")


class BusinessToolTestResponse(BaseSchema):
    """Response schema for business tool testing."""

    success: bool = Field(..., description="Whether the test was successful")
    status_code: int | None = Field(None, description="HTTP status code from the API")
    response_data: Any | None = Field(None, description="Response data from the API")
    processed_response: dict[str, Any] | None = Field(None, description="Processed response for AI")
    error_message: str | None = Field(None, description="Error message if the test failed")
    execution_time_ms: float | None = Field(None, description="Execution time in milliseconds")
    transformation_log: list[str] = Field(default_factory=list, description="Log of transformations applied")


# Business Tool Reference for Agent Configuration
class BusinessToolReference(BaseSchema):
    """Reference to a business tool with enablement status."""

    tool_id: str = Field(..., description="ID of the business tool to reference.")
    enabled: bool = Field(True, description="Whether this business tool is enabled for the assistant.")
