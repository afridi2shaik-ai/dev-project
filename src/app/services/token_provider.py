from __future__ import annotations

import time
from typing import Optional, Tuple

import jwt as pyjwt
from fastapi import Request
from loguru import logger

from app.core.config import settings
from app.services.tenant_token_service import (
    TenantTokenAuthError,
    TenantTokenConfigError,
    TenantTokenLookupError,
    TenantTokenNotFoundError,
    TenantTokenService,
    TenantTokenServiceError,
)


class TokenCacheEntry:
    def __init__(self, access_token: str, id_token: str, expires_at: float):
        self.access_token = access_token
        self.id_token = id_token
        self.expires_at = expires_at

    def is_valid(self) -> bool:
        # Small buffer to avoid edge expiry
        return time.time() < (self.expires_at - 15)


class TokenProvider:
    """Provides access/id tokens from request or by generating on behalf of tenant.

    - get_tokens_from_request: read Authorization and id_token headers
    - get_tokens_for_tenant: POST /api/auth/token/tenant using AUTH_USERNAME/PASSWORD
    """

    _cache: dict[str, TokenCacheEntry] = {}

    @staticmethod
    def get_tokens_from_request(request: Request) -> Tuple[str, str]:
        # Access token via Authorization header (Bearer preferred, also allow token only)
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise ValueError("Authorization header not provided")
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            access_token = parts[1]
        else:
            access_token = parts[0]

        id_token = request.headers.get("x-id-token") or request.headers.get("id_token")
        if not id_token:
            raise ValueError("id_token header not provided")

        return access_token, id_token

    @classmethod
    async def get_tokens_for_tenant(
        cls, tenant_id: str, *, force_refresh: bool = False
    ) -> Tuple[str, str]:
        if not tenant_id:
            raise ValueError("tenant_id is required")

        # Cached?
        entry = None if force_refresh else cls._cache.get(tenant_id)
        if entry and entry.is_valid():
            return entry.access_token, entry.id_token
        if force_refresh:
            cls._cache.pop(tenant_id, None)

        # Validate credentials
        if not settings.AUTH_USERNAME or not settings.AUTH_PASSWORD:
            raise RuntimeError("AUTH_USERNAME/AUTH_PASSWORD not configured for token generation")

        try:
            token_response = await TenantTokenService.generate_tokens(
                username=settings.AUTH_USERNAME,
                password=settings.AUTH_PASSWORD,
                tenant_id=tenant_id,
            )
        except TenantTokenNotFoundError as exc:
            logger.error(str(exc))
            raise RuntimeError(str(exc)) from exc
        except TenantTokenAuthError as exc:
            logger.error(str(exc))
            raise RuntimeError("Failed to authenticate with Auth0") from exc
        except (TenantTokenConfigError, TenantTokenLookupError, TenantTokenServiceError) as exc:
            logger.error(str(exc))
            raise RuntimeError("Failed to generate tokens for tenant") from exc

        access_token = token_response.access_token
        id_token = token_response.id_token
        expires_in = token_response.expires_in or 3600

        # Validate token has tenant_id before caching — don't cache broken tokens
        has_tenant_id = False
        try:
            claims = pyjwt.decode(access_token, options={"verify_signature": False})
            has_tenant_id = "tenant_id" in claims
        except Exception:
            logger.warning(f"Failed to decode access_token for tenant {tenant_id} — skipping cache")

        if has_tenant_id:
            expires_at = time.time() + int(expires_in)
            cls._cache[tenant_id] = TokenCacheEntry(access_token, id_token, expires_at)
            logger.debug(
                "Cached tokens for tenant {} (exp in {}s, access preview ...{}).",
                tenant_id,
                expires_in,
                access_token[-6:] if len(access_token) > 6 else access_token,
            )
        else:
            # Evict any stale entry — don't let a broken token persist
            cls._cache.pop(tenant_id, None)
            logger.warning(
                f"⚠️ NOT caching tokens for tenant {tenant_id} — access_token is missing tenant_id claim. "
                f"Token will be re-generated on next request."
            )

        return access_token, id_token

    @classmethod
    def invalidate_cache(cls, tenant_id: str) -> None:
        if tenant_id in cls._cache:
            cls._cache.pop(tenant_id, None)
            logger.debug("Token cache invalidated for tenant %s", tenant_id)
