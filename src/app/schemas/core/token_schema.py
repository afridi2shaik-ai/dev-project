"""
API Credential Schemas for Custom Token Authentication.
Supports multi-token authentication where multiple tokens (e.g., access_token + id_token)
can be extracted from a single API response and placed in different HTTP headers.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator

from app.schemas.base_schema import BaseSchema


class TokenRequestMethod(str, Enum):
    """HTTP methods supported for token requests."""

    GET = "GET"
    POST = "POST"


class TokenRequestConfig(BaseSchema):
    """Configuration for making token generation API calls."""

    endpoint: str = Field(..., description="Token endpoint URL (e.g., https://api.example.com/token)")
    method: TokenRequestMethod = Field(TokenRequestMethod.POST, description="HTTP method for token request")
    headers: dict[str, str] = Field(default_factory=dict, description="Additional headers for token request")
    body_template: dict[str, str] = Field(..., description="Request body template with sensitive fields (will be encrypted)")

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate endpoint is a valid URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Endpoint must start with http:// or https://")
        return v


class TokenConfig(BaseSchema):
    """Configuration for a single token."""

    name: str = Field(..., description="Token identifier (e.g., 'access_token', 'id_token')")
    response_path: str = Field(..., description="JSONPath to token in response (e.g., 'access_token', 'data.token')")
    header_name: str = Field("Authorization", description="HTTP header name for this token")
    header_format: str = Field("Bearer {token}", description="Header value format. Use {token} as placeholder")

    @field_validator("response_path")
    @classmethod
    def validate_response_path(cls, v: str) -> str:
        """Validate response path is not empty."""
        if not v.strip():
            raise ValueError("Response path cannot be empty")
        return v.strip()

    @field_validator("header_format")
    @classmethod
    def validate_header_format(cls, v: str) -> str:
        """Validate header format contains {token} placeholder."""
        if "{token}" not in v:
            raise ValueError("Header format must contain {token} placeholder")
        return v


class TokenResponseConfig(BaseSchema):
    """Configuration for extracting tokens from API response."""

    tokens: list[TokenConfig] = Field(..., min_length=1, description="List of tokens to extract")
    expires_in_path: str | None = Field("expires_in", description="JSONPath to expiry seconds (e.g., 'expires_in')")
    expires_in_seconds: int | None = Field(None, description="Fixed token lifetime if not in response")

    @field_validator("tokens")
    @classmethod
    def validate_unique_token_names(cls, tokens: list[TokenConfig]) -> list[TokenConfig]:
        """Ensure each token name is unique."""
        token_names = [t.name for t in tokens]
        duplicates = [name for name in token_names if token_names.count(name) > 1]

        if duplicates:
            raise ValueError(f"Duplicate token names found: {set(duplicates)}. Each token must have a unique name.")

        return tokens

    @field_validator("tokens")
    @classmethod
    def validate_unique_headers(cls, tokens: list[TokenConfig]) -> list[TokenConfig]:
        """Ensure each header_name is unique."""
        header_names = [t.header_name for t in tokens]
        duplicates = [h for h in header_names if header_names.count(h) > 1]

        if duplicates:
            raise ValueError(f"Duplicate header names found: {set(duplicates)}. Each token must use a different header.")

        return tokens

    @field_validator("expires_in_seconds")
    @classmethod
    def validate_expires_in_seconds(cls, v: int | None) -> int | None:
        """Validate expiry time is reasonable."""
        if v is not None:
            if v < 60:  # Less than 1 minute
                raise ValueError("expires_in_seconds must be at least 60 seconds")
            if v > 86400 * 30:  # More than 30 days
                raise ValueError("expires_in_seconds cannot exceed 30 days (2592000 seconds)")
        return v


class APICredential(BaseSchema):
    """API Credential with multi-token management."""

    credential_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id", description="Unique credential identifier")
    tenant_id: str
    credential_name: str = Field(..., description="Unique name for this credential")
    description: str | None = Field(None, description="Description of what this credential is for")
    api_provider: str = Field(..., description="API provider name (e.g., circuitry_ai, auth0)")

    # Token Configuration
    token_request: TokenRequestConfig
    token_response: TokenResponseConfig

    # Cached Tokens (encrypted, multiple)
    cached_tokens: dict[str, str] | None = Field(None, description="Encrypted tokens {token_name: encrypted_token}")
    token_expires_at: datetime | None = Field(None, description="When all tokens expire (earliest expiry)")
    token_cached_at: datetime | None = Field(None, description="When tokens were last cached")

    # Metadata
    is_active: bool = Field(True, description="Whether this credential is active")
    created_at: datetime
    updated_at: datetime
    created_by: dict | None = None
    updated_by: dict | None = None


class APICredentialCreateRequest(BaseSchema):
    """Request to create a new API credential."""

    credential_name: str = Field(..., description="Unique name for this credential")
    description: str | None = Field(None, description="Description of what this credential is for")
    api_provider: str = Field(..., description="API provider name (e.g., circuitry_ai, auth0)")

    # Token Configuration
    token_request: TokenRequestConfig
    token_response: TokenResponseConfig


class APICredentialUpdateRequest(BaseSchema):
    """Request to update an existing API credential."""

    credential_name: str | None = Field(None, description="New name for the credential")
    description: str | None = Field(None, description="New description")
    api_provider: str | None = Field(None, description="New API provider name")

    # Token Configuration (optional updates)
    token_request: TokenRequestConfig | None = None
    token_response: TokenResponseConfig | None = None

    # Metadata
    is_active: bool | None = Field(None, description="Update active status")


class APICredentialListItem(BaseSchema):
    """Simplified credential info for list responses (no sensitive data)."""

    id: str = Field(..., alias="_id", description="Credential ID")
    tenant_id: str
    credential_name: str
    
