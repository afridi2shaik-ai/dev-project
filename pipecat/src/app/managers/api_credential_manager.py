"""
Token Manager

Handles CRUD operations for API credentials used in custom token authentication.
"""

import datetime

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.core.token_schema import (
    APICredential,
    APICredentialCreateRequest,
    APICredentialListItem,
    APICredentialUpdateRequest,
    TokenRequestConfig,
)
from app.schemas.user_schema import UserInfo
from app.services.encryption_service import get_encryption_service


class APICredentialManager:
    """Manager for API credential CRUD operations."""

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        """Initialize Token Manager."""
        self.db = db
        self.tenant_id = tenant_id
        self.collection = db["api_credentials"]
        self.encryption_service = get_encryption_service()
        logger.debug(f"APICredentialManager initialized for tenant {tenant_id}")

    def _encrypt_sensitive_fields(self, body_template: dict) -> dict:
        """Encrypt sensitive fields in body template.
        
        Automatically detects and encrypts fields that contain sensitive keywords
        (password, secret, token, key) in their field names.
        
        Args:
            body_template: Request body template with sensitive fields.
        
        Returns:
            Body template with encrypted sensitive fields (prefixed with 'encrypted:').
        """
        encrypted_body = {}
        for key, value in body_template.items():
            if isinstance(value, str) and any(
                sensitive in key.lower() for sensitive in ["password", "secret", "token", "key"]
            ):
                # Encrypt sensitive field (prefix added by EncryptionService)
                encrypted_body[key] = self.encryption_service.encrypt(value)
            else:
                encrypted_body[key] = value
        return encrypted_body

    def _decrypt_sensitive_fields(self, body_template: dict) -> dict:
        """Decrypt sensitive fields in body template.
        
        Only decrypts values that start with 'encrypted:' prefix to avoid
        attempting to decrypt plain text values.
        """
        decrypted_body = {}
        for key, value in body_template.items():
            if isinstance(value, str) and value.startswith("encrypted:"):
                # Decrypt sensitive field (EncryptionService handles prefix)
                decrypted_body[key] = self.encryption_service.decrypt(value)
            else:
                decrypted_body[key] = value
        return decrypted_body

    async def create_credential(
        self, credential_data: APICredentialCreateRequest, user_info: UserInfo
    ) -> str:
        """Create a new API credential."""
        logger.info(f"Creating API credential: {credential_data.credential_name}")

        existing = await self.collection.find_one({
            "tenant_id": self.tenant_id,
            "credential_name": credential_data.credential_name
        })
        if existing:
            raise ValueError(f"Credential with name '{credential_data.credential_name}' already exists.")

        encrypted_body = self._encrypt_sensitive_fields(credential_data.token_request.body_template)
        token_request_dict = credential_data.token_request.model_dump()
        token_request_dict["body_template"] = encrypted_body
        encrypted_token_request = TokenRequestConfig(**token_request_dict)


        now = datetime.datetime.now(datetime.UTC)
        credential = APICredential(
            tenant_id=self.tenant_id,
            credential_name=credential_data.credential_name,
            description=credential_data.description,
            api_provider=credential_data.api_provider,
            token_request=encrypted_token_request,
            token_response=credential_data.token_response,
            is_active=True,
            created_at=now,
            updated_at=now,
            created_by=user_info.model_dump(),
            updated_by=user_info.model_dump(),
        )

        doc = credential.model_dump(by_alias=True)
        result = await self.collection.insert_one(doc)
        credential_id = str(result.inserted_id)

        # TODO: Add audit trail logging for credential creation

        logger.info(f"Created API credential {credential_id}: {credential_data.credential_name}")
        return credential_id

    async def get_credential(self, credential_id: str, decrypt: bool = True) -> APICredential | None:
        """Get an API credential by ID.
        
        Args:
            credential_id: Credential ID.
            decrypt: Whether to decrypt sensitive fields (default: True).
        
        Returns:
            APICredential or None if not found.
        """
        credential_data = await self.collection.find_one({
            "_id": credential_id,
            "tenant_id": self.tenant_id
        })

        if not credential_data:
            logger.warning(f"Credential {credential_id} not found for tenant {self.tenant_id}. It may not exist or belong to a different tenant.")
            return None

        # Decrypt sensitive fields if requested
        if decrypt and "token_request" in credential_data and "body_template" in credential_data["token_request"]:
            credential_data["token_request"]["body_template"] = self._decrypt_sensitive_fields(
                credential_data["token_request"]["body_template"]
            )

        return APICredential(**credential_data)

    async def update_credential(
        self, credential_id: str, update_data: APICredentialUpdateRequest, user_info: UserInfo
    ) -> bool:
        """Update an existing API credential.
        
        Args:
            credential_id: Credential ID.
            update_data: Update request.
            user_info: User updating the credential.
        
        Returns:
            True if updated successfully.
        
        Raises:
            ValueError: If credential not found or update validation fails.
        """
        # Get current state
        current = await self.get_credential(credential_id, decrypt=False)
        if not current:
            raise ValueError(f"Credential {credential_id} not found")

        # Build update document
        update_dict = update_data.model_dump(exclude_unset=True)

        # Encrypt sensitive fields if body_template is being updated
        if "token_request" in update_dict and "body_template" in update_dict["token_request"]:
            update_dict["token_request"]["body_template"] = self._encrypt_sensitive_fields(
                update_dict["token_request"]["body_template"]
            )

        # If token configuration changed, clear cached tokens
        if "token_request" in update_dict or "token_response" in update_dict:
            update_dict["cached_tokens"] = None
            update_dict["token_expires_at"] = None
            update_dict["token_cached_at"] = None
            logger.info(f"Token configuration changed for {credential_id}, cleared cached tokens")

        update_dict["updated_at"] = datetime.datetime.now(datetime.UTC)
        update_dict["updated_by"] = user_info.model_dump()

        # Update in database
        result = await self.collection.update_one(
            {"_id": credential_id, "tenant_id": self.tenant_id}, {"$set": update_dict}
        )

        if result.matched_count == 0:
            raise ValueError("Credential was modified by another user. Please refresh and try again.")

        # TODO: Add audit trail logging for credential update

        logger.info(f"Updated API credential {credential_id}")
        return True

    async def delete_credential(self, credential_id: str, user_info: UserInfo) -> bool:
        """Soft delete an API credential by setting is_active to False."""
        current = await self.get_credential(credential_id, decrypt=False)
        if not current:
            return False

        update_dict = {
            "is_active": False,
            "cached_tokens": None,
            "token_expires_at": None,
            "token_cached_at": None,
            "updated_at": datetime.datetime.now(datetime.UTC),
            "updated_by": user_info.model_dump(),
        }

        result = await self.collection.update_one({"_id": credential_id, "tenant_id": self.tenant_id}, {"$set": update_dict})

        if result.matched_count == 0:
            return False

        # TODO: Add audit trail logging for credential deletion

        logger.info(f"Deleted (soft) API credential {credential_id}")
        return True

    async def list_credentials(self, skip: int = 0, limit: int = 20) -> tuple[list[APICredentialListItem], int]:
        """List API credentials with pagination."""
        query = {"tenant_id": self.tenant_id}
        total_items = await self.collection.count_documents(query)

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        credentials_data = await cursor.to_list(length=limit)

        items = []
        for data in credentials_data:
            has_cached_token = bool(data.get("cached_tokens") and data.get("token_expires_at"))
            # Only pass fields allowed by APICredentialListItem (extra="forbid" on BaseSchema)
            list_item_data = {
                "_id": str(data["_id"]),  # ensure str for Pydantic
                "tenant_id": data["tenant_id"],
                "credential_name": data["credential_name"],
                
            }
            items.append(APICredentialListItem(**list_item_data))

        return items, total_items

    async def get_credential_by_name(self, name: str) -> APICredential | None:
        """Get an API credential by its unique name."""
        credential_data = await self.collection.find_one({"credential_name": name, "tenant_id": self.tenant_id, "is_active": True})
        if not credential_data:
            return None
        return await self.get_credential(credential_data["_id"])

    async def cache_tokens(self, credential_id: str, tokens: dict[str, str], expires_at: datetime) -> bool:
        """Cache new tokens for a credential."""
        encrypted_tokens = {k: self.encryption_service.encrypt(v) for k, v in tokens.items()}
        update_dict = {
            "cached_tokens": encrypted_tokens,
            "token_expires_at": expires_at,
            "token_cached_at": datetime.datetime.now(datetime.UTC),
        }
        result = await self.collection.update_one(
            {"_id": credential_id, "tenant_id": self.tenant_id}, {"$set": update_dict}
        )
        return result.modified_count > 0

    async def get_decrypted_tokens(self, credential: APICredential) -> dict[str, str] | None:
        """Get decrypted tokens from a credential object."""
        if not credential.cached_tokens:
            return None
        return {k: self.encryption_service.decrypt(v) for k, v in credential.cached_tokens.items()}
