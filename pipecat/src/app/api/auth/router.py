"""Authentication API router for token generation."""

from fastapi import APIRouter, HTTPException
from loguru import logger
from requests.exceptions import HTTPError
from starlette.requests import Request

from app.core import settings
from app.schemas.auth import TenantTokenRequest, TokenRequest, TokenResponse
from app.services.tenant_token_service import (
    TenantTokenAuthError,
    TenantTokenConfigError,
    TenantTokenLookupError,
    TenantTokenNotFoundError,
    TenantTokenService,
    TenantTokenServiceError,
)
from app.utils.auth import Auth0PasswordGrantClient

auth_router = APIRouter()


@auth_router.post("/token", response_model=TokenResponse, summary="Get User Token")
async def get_token(request: Request, data: TokenRequest):
    """Generates an access token and ID token using the Resource Owner Password Grant.
    This endpoint is unauthenticated and should be used to initiate a session.
    """
    if not settings.AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="This endpoint is not available when authentication is disabled.")

    if not all([settings.AUTH0_DOMAIN, settings.AUTH0_M2M_CLIENT_ID, settings.AUTH0_M2M_CLIENT_SECRET, settings.AUTH0_API_IDENTIFIER]):
        raise HTTPException(status_code=500, detail="Auth0 is not fully configured on the server.")

    token_generator = Auth0PasswordGrantClient(domain=settings.AUTH0_DOMAIN)

    try:
        token_data = token_generator.get_token(
            client_id=settings.AUTH0_M2M_CLIENT_ID,
            client_secret=settings.AUTH0_M2M_CLIENT_SECRET,
            audience=settings.AUTH0_API_IDENTIFIER,
            username=data.username,
            password=data.password,
            org_id=data.org_id
        )
        token_response = TokenResponse(**token_data)

        return token_response
    except HTTPError as e:
        # The response from the identity provider might contain sensitive info,
        # so we log it but return a generic error to the client.
        logger.error(f"Auth0 token request failed: {e.response.text}")
        raise HTTPException(status_code=401, detail="Invalid username, password, or organization ID.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during token generation: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")


@auth_router.post("/token/tenant", response_model=TokenResponse, summary="Get User Token by Tenant ID")
async def get_token_by_tenant(request: Request, data: TenantTokenRequest):
    """Generates an access token and ID token using tenant_id lookup.
    
    This is a convenience endpoint that automatically resolves the Auth0 organization ID
    from the tenant_id by querying the global organizations database. Everything else
    is identical to the /token endpoint.
    
    **Flow:**
    1. Query global database for organization by tenant_id
    2. Extract auth0_organization_id from organization document
    3. Use Auth0 Resource Owner Password Grant with resolved org_id
    4. Return access and ID tokens
    
    **Benefits:**
    - Users don't need to know or remember Auth0 organization IDs
    - Simpler frontend integration (just tenant_id instead of org_id)
    - Same security as /token endpoint (password still required)
    
    **Args:**
    - username: User's email address
    - password: User's password
    - tenant_id: Tenant identifier to lookup organization details
    
    **Returns:**
    - access_token: JWT access token
    - id_token: JWT ID token
    - token_type: "Bearer"
    - expires_in: Token expiration time in seconds
    
    **Errors:**
    - 404: Organization not found for tenant_id
    - 401: Invalid username or password
    - 500: Auth0 configuration error
    """
    if not settings.AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="This endpoint is not available when authentication is disabled.")

    if not all([settings.AUTH0_DOMAIN, settings.AUTH0_M2M_CLIENT_ID, settings.AUTH0_M2M_CLIENT_SECRET, settings.AUTH0_API_IDENTIFIER]):
        raise HTTPException(status_code=500, detail="Auth0 is not fully configured on the server.")

    try:
        return await TenantTokenService.generate_tokens(
            username=data.username,
            password=data.password,
            tenant_id=data.tenant_id,
        )
    except TenantTokenNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TenantTokenAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except TenantTokenLookupError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except TenantTokenConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except TenantTokenServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
