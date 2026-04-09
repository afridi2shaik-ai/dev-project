"""
Encryption Service for Sensitive Credential Data.

Provides secure encryption and decryption of sensitive fields like passwords,
API keys, and tokens using Fernet symmetric encryption.
"""

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from app.core.config import settings


class EncryptionService:
    """Service for encrypting and decrypting sensitive credential data."""

    def __init__(self):
        """Initialize encryption service with Fernet cipher."""
        if not settings.ENCRYPTION_KEY:
            raise ValueError(
                "ENCRYPTION_KEY environment variable not set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        try:
            self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
            logger.debug("EncryptionService initialized successfully")
        except Exception as e:
            raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if not data:
            raise ValueError("Cannot encrypt empty data")

        try:
            encrypted = self.cipher.encrypt(data.encode())
            encrypted_str = f"encrypted:{encrypted.decode()}"
            return encrypted_str
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Encryption failed: {e}")

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        if not encrypted_data or not encrypted_data.startswith("encrypted:"):
            return encrypted_data # Return as is if not encrypted

        encrypted = encrypted_data.replace("encrypted:", "")

        try:
            decrypted = self.cipher.decrypt(encrypted.encode())
            return decrypted.decode()
        except InvalidToken:
            raise ValueError("Decryption failed: Invalid token. The ENCRYPTION_KEY may have changed.")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Decryption failed: {e}")


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get or create singleton EncryptionService instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
