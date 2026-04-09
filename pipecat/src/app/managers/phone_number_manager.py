"""
Phone Number Manager

Handles database operations for phone numbers and provider credentials.
Retrieves and decrypts provider credentials (Plivo/Twilio) based on phone number.
"""

from typing import Tuple
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core import settings
from app.services.encryption_service import get_encryption_service


class PhoneNumberManager:
    """Manager for phone number and provider credential operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize PhoneNumberManager.
        
        Args:
            db: The MongoDB database connection (tenant-specific database).
        """
        self.db = db
        self.phone_numbers_collection = db["phone_numbers"]
        self.phone_credentials_collection = db["phone_credentials"]
        self.encryption_service = get_encryption_service()

    async def get_provider_credentials(
        self,
        phone_number: str | None,
        provider: str,
    ) -> Tuple[str, str]:
        """
        Get provider credentials (api_key/auth_id and secret/token) based on phone number.
        
        Searches for phone number in database. If found and it's an external number,
        retrieves and decrypts credentials. For internal numbers or if not found,
        falls back to default settings.
        
        Args:
            phone_number: Phone number to look up (e.g., "+14025243456")
            provider: Provider name ("plivo" or "twilio")
            
        Returns:
            Tuple of (api_key/auth_id, secret/token) for the provider
            
        Raises:
            ValueError: If provider is not supported or credentials are missing
        """
        if not phone_number:
            return self._get_default_credentials(provider)
        
        # Normalize phone number - try both with and without + prefix
        normalized_numbers = [phone_number]
        if phone_number.startswith("+"):
            normalized_numbers.append(phone_number[1:])
        else:
            normalized_numbers.append(f"+{phone_number}")
        
        # Look up phone number in database
        phone_doc = await self.phone_numbers_collection.find_one({
            "number": {"$in": normalized_numbers},
            "provider": provider,
            "is_active": True
        })
        
        if not phone_doc:
            return self._get_default_credentials(provider)
        
        # Check if it's an external number
        provider_type = phone_doc.get("provider_type")
        if provider_type != "external":
            return self._get_default_credentials(provider)
        
        # Get credentials ID for external numbers
        credentials_id = phone_doc.get("credentials")
        if not credentials_id:
            logger.warning(
                f"Phone number {phone_number} marked as external but no credentials ID found"
            )
            return self._get_default_credentials(provider)
        
        # Retrieve credentials document
        credentials_doc = await self.phone_credentials_collection.find_one({
            "_id": credentials_id
        })
        
        if not credentials_doc:
            logger.warning(
                f"Credentials document {credentials_id} not found for phone {phone_number}"
            )
            return self._get_default_credentials(provider)
        
        # Verify provider matches
        creds_provider = credentials_doc.get("provider")
        if creds_provider != provider:
            logger.warning(
                f"Provider mismatch: phone number has {provider} but credentials have {creds_provider}"
            )
            return self._get_default_credentials(provider)
        
        # Get encrypted credentials
        creds_data = credentials_doc.get("credentials", {})
        encrypted_api_key = creds_data.get("api_key")
        encrypted_secret = creds_data.get("secret")
        
        if not encrypted_api_key or not encrypted_secret:
            logger.warning(
                f"Missing credentials in document {credentials_id} for phone {phone_number}"
            )
            return self._get_default_credentials(provider)
        
        # Decrypt credentials
        try:
            api_key = self.encryption_service.decrypt(encrypted_api_key)
            secret = self.encryption_service.decrypt(encrypted_secret)
            logger.info(
                f"Retrieved {provider} credentials for external phone {phone_number}"
            )
            return api_key, secret
        except Exception as e:
            logger.error(
                f"Failed to decrypt credentials for phone {phone_number}: {e}"
            )
            return self._get_default_credentials(provider)

    def _get_default_credentials(self, provider: str) -> Tuple[str, str]:
        """Get default provider credentials from settings."""
        if provider == "plivo":
            auth_id = settings.PLIVO_AUTH_ID
            auth_token = settings.PLIVO_AUTH_TOKEN
            if not auth_id or not auth_token:
                raise ValueError("Plivo credentials not configured in settings")
            return auth_id, auth_token
        elif provider == "twilio":
            account_sid = settings.TWILIO_ACCOUNT_SID
            auth_token = settings.TWILIO_AUTH_TOKEN
            if not account_sid or not auth_token:
                raise ValueError("Twilio credentials not configured in settings")
            return account_sid, auth_token
        else:
            raise ValueError(
                f"Unsupported provider: {provider}. Supported providers: 'plivo', 'twilio'"
            )

