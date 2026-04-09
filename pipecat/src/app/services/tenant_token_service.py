from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from loguru import logger
from requests import HTTPError

from app.core import settings
from app.db.database import get_global_database
from app.managers.organization_manager import OrganizationManager
from app.schemas.auth import TokenResponse
from app.utils.auth import Auth0PasswordGrantClient


class TenantTokenServiceError(Exception):
    """Base exception for tenant token generation failures."""


class TenantTokenConfigError(TenantTokenServiceError):
    """Raised when server-side configuration is incomplete."""


class TenantTokenLookupError(TenantTokenServiceError):
    """Raised when tenant-to-organization lookup fails."""


class TenantTokenNotFoundError(TenantTokenServiceError):
    """Raised when no organization exists for the requested tenant."""


class TenantTokenAuthError(TenantTokenServiceError):
    """Raised when Auth0 rejects the supplied credentials."""


class TenantTokenService:
    """Generates Auth0 access/ID tokens for a tenant without relying on HTTP self-calls."""

    @staticmethod
    async def _resolve_auth0_org_id(tenant_id: str) -> str:
        try:
            global_db = get_global_database()
            org_manager = OrganizationManager(global_db)
            auth0_org_id = await org_manager.get_auth0_org_id_by_tenant(tenant_id)
        except HTTPException as exc:
            raise TenantTokenLookupError(exc.detail) from exc
        except Exception as exc:
            raise TenantTokenLookupError(f"Failed to lookup organization for tenant {tenant_id}: {exc}") from exc

        if not auth0_org_id:
            raise TenantTokenNotFoundError(f"Organization not found for tenant_id: {tenant_id}")
        return auth0_org_id

    @staticmethod
    async def generate_tokens(username: str, password: str, tenant_id: str) -> TokenResponse:
        if not settings.AUTH_ENABLED:
            raise TenantTokenConfigError("Authentication is disabled; token generation is unavailable.")

        required = [
            settings.AUTH0_DOMAIN,
            settings.AUTH0_M2M_CLIENT_ID,
            settings.AUTH0_M2M_CLIENT_SECRET,
            settings.AUTH0_API_IDENTIFIER,
        ]
        if not all(required):
            raise TenantTokenConfigError("Auth0 configuration is incomplete.")

        if not username or not password:
            raise TenantTokenConfigError("AUTH_USERNAME/AUTH_PASSWORD must be configured.")

        auth0_org_id = await TenantTokenService._resolve_auth0_org_id(tenant_id)

        token_generator = Auth0PasswordGrantClient(domain=settings.AUTH0_DOMAIN)

        try:
            token_data = token_generator.get_token(
                client_id=settings.AUTH0_M2M_CLIENT_ID,
                client_secret=settings.AUTH0_M2M_CLIENT_SECRET,
                audience=settings.AUTH0_API_IDENTIFIER,
                username=username,
                password=password,
                org_id=auth0_org_id,
            )
        except HTTPError as exc:
            logger.error(f"Auth0 token request failed for tenant_id {tenant_id}: {exc.response.text}")
            raise TenantTokenAuthError("Invalid username, password, or organization.") from exc
        except Exception as exc:
            raise TenantTokenServiceError(f"Unexpected error during token generation: {exc}") from exc

        return TokenResponse(**token_data)

