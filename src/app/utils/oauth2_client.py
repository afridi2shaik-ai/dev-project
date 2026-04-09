import asyncio
import base64
from datetime import datetime, timedelta

import aiohttp
from loguru import logger

from app.core.constants import EXPONENTIAL_BACKOFF_MULTIPLIER, MAX_RETRY_ATTEMPTS, RETRY_DELAY_SECONDS
from app.schemas.core.business_tool_schema import OAuth2AuthConfig


class OAuth2TokenCache:
    """Simple in-memory cache for OAuth 2.0 access tokens."""

    def __init__(self):
        self._tokens: dict[str, tuple[str, datetime]] = {}

    def get_token(self, cache_key: str) -> str | None:
        """Get a cached token if it's still valid."""
        if cache_key in self._tokens:
            token, expires_at = self._tokens[cache_key]
            if datetime.now() < expires_at:
                return token
            # Token expired, remove it
            del self._tokens[cache_key]
        return None

    def set_token(self, cache_key: str, token: str, expires_in: int, buffer_seconds: int = 60):
        """Cache a token with expiration buffer."""
        expires_at = datetime.now() + timedelta(seconds=expires_in - buffer_seconds)
        self._tokens[cache_key] = (token, expires_at)
        logger.debug(f"Cached OAuth token until {expires_at}")


# Global token cache
_token_cache = OAuth2TokenCache()


class OAuth2Client:
    """OAuth 2.0 client for handling token acquisition and management."""

    def __init__(self, config: OAuth2AuthConfig):
        self.config = config
        self.cache_key = f"{config.client_id}:{config.token_url}:{config.scope or ''}"

    async def get_access_token(self, session: aiohttp.ClientSession) -> str:
        """Get a valid access token, using cache if enabled."""
        # Check cache first if enabled
        if self.config.cache_token:
            cached_token = _token_cache.get_token(self.cache_key)
            if cached_token:
                logger.debug("Using cached OAuth access token")
                return cached_token

        # Request new token
        logger.debug(f"Requesting new OAuth access token from {self.config.token_url}")

        if self.config.grant_type == "client_credentials":
            return await self._get_client_credentials_token(session)
        if self.config.grant_type == "authorization_code":
            raise NotImplementedError("Authorization code flow requires user interaction - not supported for automated API calls")
        raise ValueError(f"Unsupported grant type: {self.config.grant_type}")

    async def _get_client_credentials_token(self, session: aiohttp.ClientSession) -> str:
        """Get access token using client credentials flow."""
        # Prepare request data
        data = {
            "grant_type": "client_credentials",
        }

        if self.config.scope:
            data["scope"] = self.config.scope

        # Prepare authentication headers
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Use Basic authentication with client credentials
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_credentials}"

        # Retry logic for token acquisition
        last_exception = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                async with session.post(self.config.token_url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        access_token = token_data.get("access_token")

                        if not access_token:
                            raise ValueError("No access_token in OAuth response")

                        # Cache the token if enabled
                        if self.config.cache_token and "expires_in" in token_data:
                            expires_in = int(token_data["expires_in"])
                            _token_cache.set_token(self.cache_key, access_token, expires_in, self.config.token_expires_buffer)

                        logger.debug("Successfully obtained OAuth access token")
                        return access_token

                    error_text = await response.text()
                    raise Exception(f"OAuth token request failed: {response.status} - {error_text}")

            except (aiohttp.ClientError, Exception) as e:
                last_exception = e
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = RETRY_DELAY_SECONDS * (EXPONENTIAL_BACKOFF_MULTIPLIER**attempt)
                    logger.warning(f"OAuth 2.0 token request failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"OAuth 2.0 token request failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")

        # If we get here, all retries failed
        raise Exception(f"OAuth 2.0 token acquisition failed after {MAX_RETRY_ATTEMPTS} attempts: {last_exception}")


async def get_oauth2_headers(config: OAuth2AuthConfig, session: aiohttp.ClientSession) -> dict[str, str]:
    """Get headers with OAuth 2.0 Bearer token for API requests."""
    client = OAuth2Client(config)
    access_token = await client.get_access_token(session)

    return {"Authorization": f"Bearer {access_token}"}
