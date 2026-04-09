"""
Auth utilities for request validation.

Validates id_token when AUTH_ENABLED; raises HTTPException on failure.
"""

from fastapi import HTTPException, Request

from app.auth0.auth_service import AuthService
from app.core.config import AUTH_ENABLED


def validate_request_auth(request: Request, payload_tenant_id: str | None) -> str | None:
    """
    Validate request auth (id_token). Verifies the token is valid; does not compare tenant_id.

    When AUTH_ENABLED:
        - Requires id_token header (or x-id-token).
        - Decodes and validates the token. Does not require or compare payload_tenant_id.
        - Raises HTTPException (401/400/403) on failure.
    When auth disabled, returns token value if present.

    Returns:
        The raw token value (without "Bearer " prefix) for use in downstream API calls,
        or None if no token was sent.
    """
    id_token = request.headers.get("id_token") or request.headers.get("x-id-token")
    token_value = (id_token.split("Bearer ")[-1].strip()) if id_token else None

    if AUTH_ENABLED:
        if id_token:
            AuthService.decode_id_token(token_value)  # validates token; raises on invalid
        else:
            raise HTTPException(status_code=401, detail="id_token header is required")

    return token_value
