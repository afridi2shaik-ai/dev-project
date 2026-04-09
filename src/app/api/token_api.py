"""
API Credentials Router

Provides REST endpoints for managing API credentials used in custom token authentication.
"""

import math

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import PaginationParams, get_current_user, get_db
from app.managers.api_credential_manager import APICredentialManager
from app.schemas.core.token_schema import (
    APICredential,
    APICredentialCreateRequest,
    APICredentialListItem,
    APICredentialUpdateRequest,
)
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.user_schema import UserInfo

token_router = APIRouter()


def create_user_info_from_token(current_user: dict) -> UserInfo:
    """Create a UserInfo object from the current user token."""
    return UserInfo(id=current_user.get("sub", ""), name=current_user.get("name"), email=current_user.get("email"), role=current_user.get("role"))


@token_router.post("", response_model=str, status_code=201)
async def create_credential(
    credential_data: APICredentialCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new API credential."""
    manager = APICredentialManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    try:
        credential_id = await manager.create_credential(credential_data, user_info)
        return credential_id
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating API credential: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@token_router.get("", response_model=PaginatedResponse[APICredentialListItem])
async def list_credentials(
    db: AsyncIOMotorDatabase = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    """List API credentials with pagination."""
    manager = APICredentialManager(db, db.name)
    credentials, total_items = await manager.list_credentials(skip=pagination.skip, limit=pagination.limit)

    total_pages = math.ceil(total_items / pagination.limit) if pagination.limit > 0 else 0

    return PaginatedResponse(total_items=total_items, total_pages=total_pages, current_page=pagination.page, data=credentials)


@token_router.get("/{credential_id}", response_model=APICredential)
async def get_credential(
    credential_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get an API credential by ID."""
    manager = APICredentialManager(db, db.name)
    credential = await manager.get_credential(credential_id)

    if not credential:
        raise HTTPException(status_code=404, detail="API credential not found")

    return credential


@token_router.put("/{credential_id}", response_model=APICredential)
async def update_credential(
    credential_id: str,
    update_data: APICredentialUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update an existing API credential."""
    manager = APICredentialManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    success = await manager.update_credential(credential_id, update_data, user_info)
    if not success:
        raise HTTPException(status_code=404, detail="API credential not found")

    updated_credential = await manager.get_credential(credential_id)
    return updated_credential


@token_router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete an API credential."""
    manager = APICredentialManager(db, db.name)
    user_info = create_user_info_from_token(current_user)

    success = await manager.delete_credential(credential_id, user_info)
    if not success:
        raise HTTPException(status_code=404, detail="API credential not found")


@token_router.post("/{credential_id}/refresh-token", status_code=200)
async def refresh_credential_token(
    credential_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Manually trigger token refresh for testing.

    This endpoint:
    1. Clears any cached tokens
    2. Fetches fresh token(s) from the token endpoint
    3. Caches them in the database
    4. Returns the token details (for testing/verification)

    **Use Case:** Testing token generation without creating a business tool.

    **Example Response:**
    ```json
    {
      "success": true,
      "credential_id": "abc123",
      "tokens_refreshed": ["access_token"],
      "token_expires_at": "2025-10-10T12:00:00Z",
      "token_cached_at": "2025-10-09T14:00:00Z",
      "message": "Successfully refreshed 1 token(s)"
    }
    ```
    """
    import aiohttp

    from app.services.token_manager import TokenManager

    manager = APICredentialManager(db, db.name)

    # Get credential
    credential = await manager.get_credential(credential_id, decrypt=False)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    if not credential.is_active:
        raise HTTPException(status_code=400, detail="Credential is not active")

    # Initialize TokenManager
    token_manager = TokenManager(db, db.name)

    try:
        # Clear cached tokens first to force refresh
        await manager.collection.update_one(
            {"_id": credential_id, "tenant_id": db.name},
            {"$set": {"cached_tokens": None, "token_expires_at": None, "token_cached_at": None}},
        )
        logger.info(f"Cleared cached tokens for credential {credential_id} before refresh")

        # Fetch fresh tokens using TokenManager
        async with aiohttp.ClientSession() as session:
            tokens = await token_manager.get_valid_tokens(credential_id, session)

        # Get updated credential to show new expiry
        updated_credential = await manager.get_credential(credential_id, decrypt=False)

        return {
            "success": True,
            "credential_id": credential_id,
            "tokens_refreshed": list(tokens.keys()),
            "token_expires_at": updated_credential.token_expires_at.isoformat() if updated_credential.token_expires_at else None,
            "token_cached_at": updated_credential.token_cached_at.isoformat() if updated_credential.token_cached_at else None,
            "message": f"Successfully refreshed {len(tokens)} token(s) from {credential.token_request.endpoint}",
        }
    except ValueError as e:
        logger.error(f"Token refresh failed for credential {credential_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Token refresh failed for credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {e!s}")


@token_router.post("/{credential_id}/verify-token", status_code=200)
async def verify_credential_token(
    credential_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Verify and decrypt cached tokens for debugging/testing.

    ⚠️ **WARNING**: This endpoint returns decrypted tokens. Use ONLY for testing/debugging!

    This endpoint:
    1. Fetches the credential
    2. Decrypts all cached tokens
    3. Returns token details (first/last 20 chars shown for security)

    **Use Case:** Verify token generation and check token content.

    **Example Response:**
    ```json
    {
      "success": true,
      "credential_id": "abc123",
      "tokens": {
        "access_token": {
          "preview": "eyJhbGciOiJSUzI1NiI...dQE-wyB3BNXsyEPNyP",
          "length": 1859,
          "cached_at": "2025-10-09T14:00:00Z",
          "expires_at": "2025-10-10T14:00:00Z"
        }
      },
      "is_expired": false,
      "time_until_expiry": "23h 59m"
    }
    ```
    """
    from datetime import UTC, datetime

    from app.services.encryption_service import get_encryption_service

    manager = APICredentialManager(db, db.name)
    encryption_service = get_encryption_service()

    # Get credential
    credential = await manager.get_credential(credential_id, decrypt=False)
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    if not credential.is_active:
        raise HTTPException(status_code=400, detail="Credential is not active")

    # Check if tokens are cached
    if not credential.cached_tokens:
        return {
            "success": False,
            "credential_id": credential_id,
            "message": "No tokens cached. Use /refresh-token to generate tokens first.",
            "tokens": {},
        }

    try:
        # Decrypt all tokens
        decrypted_tokens = {}
        for token_name, encrypted_token in credential.cached_tokens.items():
            decrypted_token = encryption_service.decrypt(encrypted_token)

            # Show preview (first 20 and last 20 chars for security)
            preview = f"{decrypted_token[:20]}...{decrypted_token[-20:]}" if len(decrypted_token) > 40 else decrypted_token

            decrypted_tokens[token_name] = {
                "preview": preview,
                "full_token": decrypted_token,  # ⚠️ Full token for testing
                "length": len(decrypted_token),
                "cached_at": credential.token_cached_at.isoformat() if credential.token_cached_at else None,
                "expires_at": credential.token_expires_at.isoformat() if credential.token_expires_at else None,
            }

        # Calculate time until expiry
        is_expired = False
        time_until_expiry = None
        if credential.token_expires_at:
            # Ensure both datetimes are timezone-aware for comparison
            now = datetime.now(UTC)
            expires_at = credential.token_expires_at

            # If expires_at is naive, make it timezone-aware (assume UTC)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            if expires_at > now:
                delta = expires_at - now
                hours = delta.total_seconds() // 3600
                minutes = (delta.total_seconds() % 3600) // 60
                time_until_expiry = f"{int(hours)}h {int(minutes)}m"
            else:
                is_expired = True
                time_until_expiry = "EXPIRED"

        logger.warning(
            f"⚠️ Token verification endpoint used for credential {credential_id}. "
            "Decrypted tokens were returned in API response."
        )

        return {
            "success": True,
            "credential_id": credential_id,
            "credential_name": credential.credential_name,
            "tokens": decrypted_tokens,
            "is_expired": is_expired,
            "time_until_expiry": time_until_expiry,
            "warning": "⚠️ This endpoint returns decrypted tokens. Use only for testing!",
        }
    except Exception as e:
        logger.error(f"Token verification failed for credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Token verification failed: {e!s}")
