"""
Authentication Handler

Handles various authentication methods for business tools.
Supports Bearer tokens, API keys, Basic auth, OAuth 2.0, and custom headers.
"""

import base64
import os
import re

import aiohttp
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.managers.api_credential_manager import APICredentialManager
from app.schemas.core.business_tool_schema import (
    ApiKeyAuthConfig,
    AuthConfig,
    BasicAuthConfig,
    BearerAuthConfig,
    CustomAuthConfig,
    CustomTokenDBAuthConfig,
    OAuth2AuthConfig,
)
from app.services.token_manager import TokenManager
from app.utils.oauth2_client import OAuth2Client


class AuthenticationHandler:
    """Handles authentication for API calls."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None, tenant_id: str | None = None):
        """Initialize Authentication Handler."""
        self._oauth_clients = {}
        self.db = db
        self.tenant_id = tenant_id
        # Note: This is a simplified manager for the purpose of this example.
        # In a real app, this would be a more robust service.
        self.credential_manager = APICredentialManager(db, tenant_id) if db is not None and tenant_id else None
        self.token_manager = TokenManager(db, tenant_id) if db is not None and tenant_id else None
        logger.debug(
            f"AuthenticationHandler initialized (db: {db is not None}, tenant_id: {tenant_id}, "
            f"credential_manager: {self.credential_manager is not None}, token_manager: {self.token_manager is not None})"
        )

    async def get_headers(self, auth_config: AuthConfig | None, aiohttp_session: aiohttp.ClientSession | None = None) -> dict[str, str]:
        """Get authentication headers for the given configuration."""

        if not auth_config:
            return {}

        if isinstance(auth_config, BearerAuthConfig):
            return await self._get_bearer_headers(auth_config)

        elif isinstance(auth_config, ApiKeyAuthConfig):
            return await self._get_api_key_headers(auth_config)

        elif isinstance(auth_config, BasicAuthConfig):
            return await self._get_basic_auth_headers(auth_config)

        elif isinstance(auth_config, OAuth2AuthConfig):
            return await self._get_oauth2_headers(auth_config)

        elif isinstance(auth_config, CustomAuthConfig):
            return await self._get_custom_headers(auth_config)

        elif isinstance(auth_config, CustomTokenDBAuthConfig):
            return await self._get_custom_token_db_headers(auth_config, aiohttp_session)

        else:
            logger.warning(f"Unknown authentication type: {type(auth_config)}")
            return {}

    async def _get_bearer_headers(self, config: BearerAuthConfig) -> dict[str, str]:
        """Get Bearer token headers."""
        token = self._resolve_env_variables(config.token)
        return {"Authorization": f"Bearer {token}"}

    async def _get_api_key_headers(self, config: ApiKeyAuthConfig) -> dict[str, str]:
        """Get API key headers."""
        api_key = self._resolve_env_variables(config.api_key)
        return {config.header_name: api_key}

    async def _get_basic_auth_headers(self, config: BasicAuthConfig) -> dict[str, str]:
        """Get Basic authentication headers."""
        username = self._resolve_env_variables(config.username)
        password = self._resolve_env_variables(config.password)

        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        return {"Authorization": f"Basic {encoded_credentials}"}

    async def _get_oauth2_headers(self, config: OAuth2AuthConfig) -> dict[str, str]:
        """Get OAuth 2.0 headers."""

        # Create or get cached OAuth client
        client_key = f"{config.client_id}:{config.token_url}"
        if client_key not in self._oauth_clients:
            self._oauth_clients[client_key] = OAuth2Client(config)

        oauth_client = self._oauth_clients[client_key]

        # Get access token (will be cached if enabled)
        async with aiohttp.ClientSession() as session:
            access_token = await oauth_client.get_access_token(session)

        return {"Authorization": f"Bearer {access_token}"}

    async def _get_custom_headers(self, config: CustomAuthConfig) -> dict[str, str]:
        """Get custom authentication headers."""
        headers = {}

        for header_name, header_value in config.headers.items():
            resolved_value = self._resolve_env_variables(header_value)
            headers[header_name] = resolved_value

        return headers

    async def _get_custom_token_db_headers(
        self, config: CustomTokenDBAuthConfig, aiohttp_session: aiohttp.ClientSession | None
    ) -> dict[str, str]:
        """Get headers for database-backed custom token auth."""
        if not self.token_manager:
            raise ValueError("Database-backed token authentication requires a database connection.")

        if not aiohttp_session:
            raise ValueError("Database-backed token authentication requires aiohttp session for token refresh.")

        # This will handle fetching, validating, and refreshing the token
        tokens = await self.token_manager.get_valid_tokens(config.credential_id, aiohttp_session)

        # We need the credential object to map tokens to headers
        credential = await self.token_manager.credential_manager.get_credential(config.credential_id)
        if not credential:
            raise ValueError(f"Credential {config.credential_id} not found during header construction")


        headers = {}
        for token_config in credential.token_response.tokens:
            token_name = token_config.name
            if token_name not in tokens:
                logger.warning(f"Token '{token_name}' not found in refreshed tokens for credential {config.credential_id}")
                continue
            token_value = tokens[token_name]
            header_name = token_config.header_name
            header_format = token_config.header_format
            header_value = header_format.replace("{token}", token_value)
            headers[header_name] = header_value
        return headers

    def _resolve_env_variables(self, value: str) -> str:
        """Resolve environment variables in configuration values.

        First tries to get values from centralized settings, then falls back to
        os.getenv for dynamic user-defined environment variables.
        """
        from app.core.config import settings

        # Pattern to match {{ENV_VAR}} syntax
        pattern = r"\{\{([^}]+)\}\}"

        def replace_env_var(match):
            env_var_name = match.group(1)

            # First try to get from centralized settings
            if hasattr(settings, env_var_name):
                env_value = getattr(settings, env_var_name)
                if env_value is not None:
                    return str(env_value)

            # Fall back to os.getenv for dynamic user-defined variables
            # This is acceptable here since it's for user-configurable templates
            env_value = os.getenv(env_var_name)

            if env_value is None:
                logger.warning(f"Environment variable '{env_var_name}' not found in settings or environment")
                return match.group(0)  # Return original if not found

            return env_value

        return re.sub(pattern, replace_env_var, value)

    def clear_oauth_cache(self):
        """Clear OAuth client cache."""
        self._oauth_clients.clear()
        logger.info("OAuth client cache cleared")
