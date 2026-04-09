"""
Token Manager for Custom Token Authentication.

Handles token lifecycle: validation, refresh, generation, and caching.
Supports multi-token authentication with concurrent refresh protection.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import aiohttp
import jwt
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.managers.api_credential_manager import APICredentialManager
from app.schemas.core.token_schema import APICredential, TokenRequestConfig
from app.services.encryption_service import get_encryption_service


class TokenManager:
    """Manages token lifecycle for database-backed custom authentication."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        self.credential_manager = APICredentialManager(db, tenant_id)
        self.encryption_service = get_encryption_service()
        self._refresh_locks: dict[str, asyncio.Lock] = {}
        logger.debug(f"TokenManager initialized for tenant {tenant_id}")

    async def get_valid_tokens(
        self, credential_id: str, aiohttp_session: aiohttp.ClientSession
    ) -> dict[str, str]:
        """Get valid tokens, refreshing if expired."""
        credential = await self.credential_manager.get_credential(credential_id)
        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        if not credential.is_active:
            raise ValueError(f"Credential {credential_id} is inactive.")

        if self._is_token_valid(credential):
            decrypted_tokens = await self.credential_manager.get_decrypted_tokens(credential)
            logger.debug(f"Using cached tokens for credential {credential_id}")
            return decrypted_tokens

        logger.info(
            f"Tokens expired or not cached for credential {credential_id}, refreshing... "
            f"(Database expiry: {credential.token_expires_at})"
        )
        return await self._refresh_tokens(credential, aiohttp_session)

    def _is_token_valid(self, credential: APICredential) -> bool:
        """Check if cached tokens are valid using two-layer validation.
        
        Layer 1: Database expiry check (always performed)
        Layer 2: JWT expiry validation (only for JWT tokens with exp claim)
        """
        if not credential.cached_tokens:
            logger.debug(f"No cached tokens for credential {credential.credential_id}")
            return False

        if not credential.token_expires_at:
            logger.debug(f"No token expiry set for credential {credential.credential_id}")
            return False

        # Layer 1: Database expiry check
        expires_at = credential.token_expires_at
        buffer_time = datetime.now(UTC) + timedelta(minutes=5)

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        db_expiry_valid = expires_at > buffer_time

        if not db_expiry_valid:
            logger.debug(
                f"Database expiry check failed for credential {credential.credential_id}. "
                f"Expires at: {expires_at}, Buffer time: {buffer_time}"
            )
            return False

        logger.debug(f"✅ Database expiry valid for credential {credential.credential_id}")

        # Layer 2: JWT expiry validation (optional, only for JWT tokens)
        jwt_expiry_valid = self._validate_jwt_expiry(credential.cached_tokens)

        if not jwt_expiry_valid:
            logger.warning(
                f"⚠️ JWT expiry validation failed even though database expiry was valid! "
                f"Credential: {credential.credential_id}"
            )
            return False

        return True

    def _validate_jwt_expiry(self, cached_tokens: dict[str, str]) -> bool:
        """Validate JWT token expiry claims, gracefully skip non-JWT tokens.
        
        This method provides Layer 2 validation:
        - Only validates tokens that are JWTs (have exactly 2 dots)
        - Only validates JWTs that have an 'exp' claim
        - Gracefully skips non-JWT tokens or JWTs without exp
        - Returns False only if a JWT token is actually expired
        
        Returns:
            bool: True if all tokens are valid or validation skipped, False if any JWT is expired
        """
        for token_name, encrypted_token in cached_tokens.items():
            try:
                # Decrypt the token
                decrypted_token = self.encryption_service.decrypt(encrypted_token)

                # Check if token has JWT structure (exactly 2 dots)
                if decrypted_token.count(".") != 2:
                    logger.debug(
                        f"Token '{token_name}' is not a JWT (no JWT structure), "
                        f"skipping JWT validation"
                    )
                    continue  # Not a JWT, skip validation

                # Try to decode as JWT
                try:
                    # Decode without signature verification (we just need the payload)
                    payload = jwt.decode(
                        decrypted_token,
                        options={"verify_signature": False}
                    )
                except jwt.DecodeError:
                    logger.debug(
                        f"Token '{token_name}' looks like JWT but cannot decode, "
                        f"skipping JWT validation"
                    )
                    continue  # Cannot decode, skip validation

                # Check if JWT has exp claim
                if "exp" not in payload:
                    logger.debug(
                        f"Token '{token_name}' has no 'exp' claim, "
                        f"skipping JWT expiry check"
                    )
                    continue  # No exp claim, skip validation

                # Validate JWT expiry with 5-minute buffer
                try:
                    token_expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
                    buffer_time = datetime.now(UTC) + timedelta(minutes=5)

                    if token_expires_at <= buffer_time:
                        logger.warning(
                            f"❌ JWT token '{token_name}' is EXPIRED! "
                            f"exp={token_expires_at.isoformat()}, "
                            f"current_time={datetime.now(UTC).isoformat()}, "
                            f"buffer_time={buffer_time.isoformat()}"
                        )
                        return False  # JWT is expired!

                    logger.debug(
                        f"✅ JWT token '{token_name}' expiry is valid. "
                        f"Expires at: {token_expires_at.isoformat()}"
                    )

                except (ValueError, OSError) as e:
                    logger.warning(
                        f"Could not parse exp timestamp for token '{token_name}': {e}, "
                        f"skipping JWT validation"
                    )
                    continue  # Cannot parse timestamp, skip validation

            except Exception as e:
                logger.error(
                    f"Error validating JWT expiry for token '{token_name}': {e}, "
                    f"skipping JWT validation for this token"
                )
                continue  # Error occurred, skip validation for this token

        return True  # All tokens are valid or validation was skipped

    async def _refresh_tokens(
        self, credential: APICredential, aiohttp_session: aiohttp.ClientSession
    ) -> dict[str, str]:
        """Refresh tokens with concurrent request protection."""
        lock = self._refresh_locks.setdefault(credential.credential_id, asyncio.Lock())

        async with lock:
            fresh_credential = await self.credential_manager.get_credential(credential.credential_id)
            if self._is_token_valid(fresh_credential):
                logger.debug(f"Tokens already refreshed for {credential.credential_id}")
                return await self.credential_manager.get_decrypted_tokens(fresh_credential)

            new_tokens, expires_at = await self._generate_tokens(
                credential.token_request, credential.token_response, aiohttp_session
            )

            await self.credential_manager.cache_tokens(credential.credential_id, new_tokens, expires_at)
            logger.info(
                f"Successfully refreshed {len(new_tokens)} token(s) for credential {credential.credential_id}. "
                f"New expiry: {expires_at.isoformat()}"
            )
            return new_tokens

    async def _generate_tokens(
        self, token_request: TokenRequestConfig, token_response_config, aiohttp_session: aiohttp.ClientSession
    ) -> tuple[dict[str, str], datetime]:
        """Call token endpoint to generate new tokens."""
        # Decrypt sensitive fields that have the 'encrypted:' prefix
        decrypted_body = {
            k: self.encryption_service.decrypt(v) if isinstance(v, str) and v.startswith("encrypted:") else v
            for k, v in token_request.body_template.items()
        }

        async with aiohttp_session.request(
            method=token_request.method.value,
            url=token_request.endpoint,
            json=decrypted_body,
            headers=token_request.headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise ValueError(f"Token generation failed with status {response.status}: {error_text}")
            response_data = await response.json()

        extracted_tokens = {}
        for token_config in token_response_config.tokens:
            token_value = self._extract_value_from_response(response_data, token_config.response_path)
            extracted_tokens[token_config.name] = token_value

        expires_at = self._calculate_expiry(response_data, token_response_config)
        return extracted_tokens, expires_at

    def _extract_value_from_response(self, response_data: dict, path: str) -> any:
        """Extract a value from response using dot-notation path."""
        parts = path.split(".")
        current = response_data
        for part in parts:
            if part not in current:
                raise ValueError(f"Key '{part}' not found in response.")
            current = current[part]
        return current

    def _calculate_expiry(self, response_data, config) -> datetime:
        """Calculate token expiry time."""
        if config.expires_in_path:
            try:
                expires_in = int(self._extract_value_from_response(response_data, config.expires_in_path))
                return datetime.now(UTC) + timedelta(seconds=expires_in)
            except (ValueError, TypeError):
                logger.warning("Could not extract expires_in from response, using fallback.")

        if config.expires_in_seconds:
            return datetime.now(UTC) + timedelta(seconds=config.expires_in_seconds)

        return datetime.now(UTC) + timedelta(days=1)
