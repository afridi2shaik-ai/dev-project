"""Authentication schemas for token generation and validation."""

from pydantic import EmailStr, Field

from app.schemas.base_schema import BaseSchema


class TokenRequest(BaseSchema):
    """Request body for generating an authentication token."""

    username: EmailStr = Field(..., description="The user's email address.")
    password: str = Field(..., description="The user's password.")
    org_id: str = Field(..., description="The ID of the Auth0 Organization the user is logging into.")


class TenantTokenRequest(BaseSchema):
    """Request body for generating an authentication token using tenant_id lookup."""

    username: EmailStr = Field(..., description="The user's email address.")
    password: str = Field(..., description="The user's password.")
    tenant_id: str = Field(..., description="The tenant ID to lookup Auth0 organization ID from global database.")


class TokenResponse(BaseSchema):
    """Response body containing the authentication tokens for a user."""

    access_token: str
    scope: str
    id_token: str
    token_type: str
    expires_in: int


class M2MTokenResponse(BaseSchema):
    """Response body containing the access token for an M2M client."""

    access_token: str
    token_type: str
    expires_in: int
