"""
Business Tool Manager

This manager handles CRUD operations for business tools according to the Domain-Driven Design
architecture. It provides proper audit trail features and follows the established patterns
from other managers in the application.

Security: All authentication credentials are encrypted at rest using Fernet encryption.
"""

import datetime
from typing import Any

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.core.business_tool_schema import (
    BusinessTool,
    BusinessToolCreateRequest,
    BusinessToolListItem,
    BusinessToolUpdateRequest,
)
from app.schemas.user_schema import UserInfo
from app.services.encryption_service import get_encryption_service


class BusinessToolManager:
    """Manager for business tool CRUD operations with encrypted credentials.
    
    Security Features:
    - Encrypts all authentication credentials (Bearer, API Key, Basic, OAuth2, Custom)
    - Uses Fernet symmetric encryption with environment-based key
    - Credentials encrypted before storage, decrypted on retrieval
    - CustomTokenDB auth uses separate encrypted storage (already secure)
    """

    def __init__(self, db: AsyncIOMotorDatabase, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.collection = db["tools"]
        self.encryption_service = get_encryption_service()

    async def create_tool(self, tool_data: BusinessToolCreateRequest, user_info: UserInfo) -> str:
        """Create a new business tool."""
        logger.info(f"Creating business tool: {tool_data.name}")

        # Check if tool name already exists for this tenant
        existing = await self.collection.find_one({"tenant_id": self.tenant_id, "name": tool_data.name})
        if existing:
            raise ValueError(f"Tool with name '{tool_data.name}' already exists")

        # Validate credential_id if using custom_token_db authentication
        await self._validate_credential_id(tool_data.api_config)

        # Create the business tool
        now = datetime.datetime.now(datetime.UTC)
        business_tool = BusinessTool(
            tenant_id=self.tenant_id,
            name=tool_data.name,
            description=tool_data.description,
            parameters=tool_data.parameters,
            pre_requests=tool_data.pre_requests,
            api_config=tool_data.api_config,
            engaging_words=tool_data.engaging_words,
            created_at=now,
            updated_at=now,
            created_by=user_info,
            updated_by=user_info,
        )

        # Encrypt authentication credentials before saving
        doc = business_tool.model_dump(by_alias=True)
        if doc.get("api_config") and doc["api_config"].get("authentication"):
            doc["api_config"]["authentication"] = self._encrypt_auth_credentials(
                doc["api_config"]["authentication"]
            )
            logger.info(f"Encrypted authentication credentials for tool: {tool_data.name}")
        
        # Insert into database
        result = await self.collection.insert_one(doc)
        tool_id = str(result.inserted_id)

        logger.info(f"Created business tool {tool_id}: {tool_data.name}")
        return tool_id

    async def get_tool(self, tool_id: str) -> BusinessTool | None:
        """Get a business tool by ID with decrypted credentials."""
        tool_data = await self.collection.find_one({"_id": tool_id, "tenant_id": self.tenant_id})

        if not tool_data:
            return None

        # Decrypt authentication credentials
        if tool_data.get("api_config") and tool_data["api_config"].get("authentication"):
            tool_data["api_config"]["authentication"] = self._decrypt_auth_credentials(
                tool_data["api_config"]["authentication"]
            )
            logger.debug(f"Decrypted authentication credentials for tool: {tool_id}")

        return BusinessTool(**tool_data)

    async def get_tools_by_ids(self, tool_ids: list[str]) -> dict[str, BusinessTool]:
        """Get multiple business tools by their IDs with decrypted credentials."""
        if not tool_ids:
            return {}

        cursor = self.collection.find({"_id": {"$in": tool_ids}, "tenant_id": self.tenant_id})

        tools = {}
        async for tool_data in cursor:
            # Decrypt authentication credentials
            if tool_data.get("api_config") and tool_data["api_config"].get("authentication"):
                tool_data["api_config"]["authentication"] = self._decrypt_auth_credentials(
                    tool_data["api_config"]["authentication"]
                )
            
            tool = BusinessTool(**tool_data)
            tools[tool.tool_id] = tool

        return tools

    async def update_tool(self, tool_id: str, update_data: BusinessToolUpdateRequest, user_info: UserInfo) -> bool:
        """Update an existing business tool."""
        # Get the current state
        current_tool = await self.get_tool(tool_id)
        if not current_tool:
            return False

        # Validate credential_id if api_config is being updated
        if update_data.api_config:
            await self._validate_credential_id(update_data.api_config)

        # Prepare update data
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict["updated_at"] = datetime.datetime.now(datetime.UTC)
        update_dict["updated_by"] = user_info.model_dump()

        # Encrypt authentication credentials if being updated
        if "api_config" in update_dict and update_dict["api_config"]:
            if isinstance(update_dict["api_config"], dict) and update_dict["api_config"].get("authentication"):
                update_dict["api_config"]["authentication"] = self._encrypt_auth_credentials(
                    update_dict["api_config"]["authentication"]
                )
                logger.info(f"Encrypted updated authentication credentials for tool: {tool_id}")

        # Update the tool
        result = await self.collection.update_one({"_id": tool_id, "tenant_id": self.tenant_id}, {"$set": update_dict})

        return result.modified_count > 0

    async def delete_tool(self, tool_id: str, user_info: UserInfo) -> bool:
        """Delete a business tool."""
        # Get the current state
        current_tool = await self.get_tool(tool_id)
        if not current_tool:
            return False

        # Delete the tool
        result = await self.collection.delete_one({"_id": tool_id, "tenant_id": self.tenant_id})

        return result.deleted_count > 0

    async def list_tools(self, skip: int = 0, limit: int = 20) -> tuple[list[BusinessToolListItem], int]:
        """List business tools with pagination."""
        # Get total count
        total_items = await self.collection.count_documents({"tenant_id": self.tenant_id})

        # Get paginated results
        projection = {"name": 1, "description": 1, "parameters": 1, "created_at": 1, "updated_at": 1}

        cursor = self.collection.find({"tenant_id": self.tenant_id}, projection).sort("created_at", -1).skip(skip).limit(limit)

        tools = []
        async for doc in cursor:
            tool_item = BusinessToolListItem(_id=doc["_id"], name=doc["name"], description=doc["description"], parameter_count=len(doc.get("parameters", [])), created_at=doc.get("created_at"), updated_at=doc.get("updated_at"))
            tools.append(tool_item)

        return tools, total_items

    async def validate_tool_ids(self, tool_ids: list[str]) -> tuple[list[str], list[str]]:
        """Validate that business tool IDs exist and are accessible."""
        if not tool_ids:
            return [], []

        # Find existing tools
        existing_tools = await self.collection.find({"_id": {"$in": tool_ids}, "tenant_id": self.tenant_id}, {"_id": 1}).to_list(length=None)

        existing_ids = [str(doc["_id"]) for doc in existing_tools]
        missing_ids = [tool_id for tool_id in tool_ids if tool_id not in existing_ids]

        return existing_ids, missing_ids

    async def get_tool_categories(self) -> list[str]:
        """Get distinct categories of business tools for this tenant."""
        # For now, return empty list as categories are not implemented in the simplified schema
        # This can be extended when categories are added back
        return []

    async def _validate_credential_id(self, api_config) -> None:
        """Validate that credential_id exists if using custom_token_db authentication.
        
        Raises:
            ValueError: If credential_id is invalid or doesn't exist
        """
        # Check if authentication is configured and is custom_token_db type
        if not api_config.authentication:
            return

        # Check if it's custom_token_db authentication
        if hasattr(api_config.authentication, "type") and api_config.authentication.type == "custom_token_db":
            credential_id = getattr(api_config.authentication, "credential_id", None)

            if not credential_id:
                raise ValueError("credential_id is required for custom_token_db authentication")

            # Validate that the credential exists
            from app.managers.api_credential_manager import APICredentialManager

            credential_manager = APICredentialManager(self.db, self.tenant_id)
            credential = await credential_manager.get_credential(credential_id)

            if not credential:
                raise ValueError(f"Invalid credential_id: '{credential_id}' does not exist")

            if not credential.is_active:
                raise ValueError(f"Credential '{credential_id}' is not active")

    def _encrypt_auth_credentials(self, auth_config: dict[str, Any] | None) -> dict[str, Any] | None:
        """Encrypt sensitive fields in authentication configuration.
        
        Encrypts credentials for all auth types except CustomTokenDB (already encrypted separately).
        
        Supported auth types:
        - bearer: Encrypts token field
        - api_key: Encrypts api_key field
        - basic: Encrypts username and password fields
        - oauth2: Encrypts client_secret field
        - custom: Encrypts all header values
        - custom_token_db: Skips encryption (uses separate encrypted storage)
        
        Args:
            auth_config: Authentication configuration dictionary
            
        Returns:
            Authentication config with encrypted sensitive fields
        """
        if not auth_config or not isinstance(auth_config, dict):
            return auth_config
        
        # CustomTokenDB uses separate encrypted storage - skip encryption
        if auth_config.get("type") == "custom_token_db":
            logger.debug("Skipping encryption for custom_token_db (uses separate encrypted storage)")
            return auth_config
        
        # Create a copy to avoid modifying original
        encrypted_config = auth_config.copy()
        auth_type = encrypted_config.get("type")
        
        try:
            # Bearer Token - encrypt token field
            if auth_type == "bearer":
                if "token" in encrypted_config and encrypted_config["token"]:
                    # Skip if already encrypted
                    if not encrypted_config["token"].startswith("encrypted:"):
                        encrypted_config["token"] = self.encryption_service.encrypt(encrypted_config["token"])
                        logger.debug("Encrypted Bearer token")
            
            # API Key - encrypt api_key field
            elif auth_type == "api_key":
                if "api_key" in encrypted_config and encrypted_config["api_key"]:
                    if not encrypted_config["api_key"].startswith("encrypted:"):
                        encrypted_config["api_key"] = self.encryption_service.encrypt(encrypted_config["api_key"])
                        logger.debug("Encrypted API key")
            
            # Basic Auth - encrypt username and password
            elif auth_type == "basic":
                if "username" in encrypted_config and encrypted_config["username"]:
                    if not encrypted_config["username"].startswith("encrypted:"):
                        encrypted_config["username"] = self.encryption_service.encrypt(encrypted_config["username"])
                if "password" in encrypted_config and encrypted_config["password"]:
                    if not encrypted_config["password"].startswith("encrypted:"):
                        encrypted_config["password"] = self.encryption_service.encrypt(encrypted_config["password"])
                        logger.debug("Encrypted Basic auth credentials")
            
            # OAuth2 - encrypt client_secret
            elif auth_type == "oauth2":
                if "client_secret" in encrypted_config and encrypted_config["client_secret"]:
                    if not encrypted_config["client_secret"].startswith("encrypted:"):
                        encrypted_config["client_secret"] = self.encryption_service.encrypt(encrypted_config["client_secret"])
                        logger.debug("Encrypted OAuth2 client_secret")
            
            # Custom Headers - encrypt all header values
            elif auth_type == "custom":
                if "headers" in encrypted_config and isinstance(encrypted_config["headers"], dict):
                    encrypted_headers = {}
                    for key, value in encrypted_config["headers"].items():
                        if value and isinstance(value, str):
                            # Skip if already encrypted
                            if not value.startswith("encrypted:"):
                                encrypted_headers[key] = self.encryption_service.encrypt(value)
                            else:
                                encrypted_headers[key] = value
                        else:
                            encrypted_headers[key] = value
                    encrypted_config["headers"] = encrypted_headers
                    logger.debug(f"Encrypted {len(encrypted_headers)} custom headers")
            
            return encrypted_config
            
        except Exception as e:
            logger.error(f"Failed to encrypt authentication credentials: {e}")
            raise ValueError(f"Credential encryption failed: {e}")
    
    def _decrypt_auth_credentials(self, auth_config: dict[str, Any] | None) -> dict[str, Any] | None:
        """Decrypt sensitive fields in authentication configuration.
        
        Decrypts credentials for all auth types except CustomTokenDB (handled separately).
        
        Supported auth types:
        - bearer: Decrypts token field
        - api_key: Decrypts api_key field
        - basic: Decrypts username and password fields
        - oauth2: Decrypts client_secret field
        - custom: Decrypts all header values
        - custom_token_db: Skips decryption (uses separate encrypted storage)
        
        Args:
            auth_config: Authentication configuration dictionary with encrypted fields
            
        Returns:
            Authentication config with decrypted sensitive fields
        """
        if not auth_config or not isinstance(auth_config, dict):
            return auth_config
        
        # CustomTokenDB uses separate encrypted storage - skip decryption
        if auth_config.get("type") == "custom_token_db":
            return auth_config
        
        # Create a copy to avoid modifying original
        decrypted_config = auth_config.copy()
        auth_type = decrypted_config.get("type")
        
        try:
            # Bearer Token - decrypt token field
            if auth_type == "bearer":
                if "token" in decrypted_config and decrypted_config["token"]:
                    if decrypted_config["token"].startswith("encrypted:"):
                        decrypted_config["token"] = self.encryption_service.decrypt(decrypted_config["token"])
                        logger.debug("Decrypted Bearer token")
            
            # API Key - decrypt api_key field
            elif auth_type == "api_key":
                if "api_key" in decrypted_config and decrypted_config["api_key"]:
                    if decrypted_config["api_key"].startswith("encrypted:"):
                        decrypted_config["api_key"] = self.encryption_service.decrypt(decrypted_config["api_key"])
                        logger.debug("Decrypted API key")
            
            # Basic Auth - decrypt username and password
            elif auth_type == "basic":
                if "username" in decrypted_config and decrypted_config["username"]:
                    if decrypted_config["username"].startswith("encrypted:"):
                        decrypted_config["username"] = self.encryption_service.decrypt(decrypted_config["username"])
                if "password" in decrypted_config and decrypted_config["password"]:
                    if decrypted_config["password"].startswith("encrypted:"):
                        decrypted_config["password"] = self.encryption_service.decrypt(decrypted_config["password"])
                        logger.debug("Decrypted Basic auth credentials")
            
            # OAuth2 - decrypt client_secret
            elif auth_type == "oauth2":
                if "client_secret" in decrypted_config and decrypted_config["client_secret"]:
                    if decrypted_config["client_secret"].startswith("encrypted:"):
                        decrypted_config["client_secret"] = self.encryption_service.decrypt(decrypted_config["client_secret"])
                        logger.debug("Decrypted OAuth2 client_secret")
            
            # Custom Headers - decrypt all header values
            elif auth_type == "custom":
                if "headers" in decrypted_config and isinstance(decrypted_config["headers"], dict):
                    decrypted_headers = {}
                    for key, value in decrypted_config["headers"].items():
                        if value and isinstance(value, str) and value.startswith("encrypted:"):
                            decrypted_headers[key] = self.encryption_service.decrypt(value)
                        else:
                            decrypted_headers[key] = value
                    decrypted_config["headers"] = decrypted_headers
                    logger.debug(f"Decrypted {len(decrypted_headers)} custom headers")
            
            return decrypted_config
            
        except Exception as e:
            logger.error(f"Failed to decrypt authentication credentials: {e}")
            raise ValueError(f"Credential decryption failed. Data may be corrupted or encrypted with a different key: {e}")
