from typing import ClassVar

import jwt
import requests
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from app.core.config import settings


class AuthService:
    """A service class for handling authentication and authorization."""

    _public_keys_cache: ClassVar[dict] = {}

    @staticmethod
    def get_auth0_public_key(kid: str):
        """Fetches the public key from Auth0's JWKS endpoint with caching."""
        if kid in AuthService._public_keys_cache:
            return AuthService._public_keys_cache[kid]

        try:
            # Failsafe: Strip quotes from the domain to prevent resolution errors.
            domain = (settings.AUTH0_DOMAIN or "").strip().strip("'\"")
            if not domain:
                raise ValueError("AUTH0_DOMAIN is not configured.")

            url = f"https://{domain}/.well-known/jwks.json"
            response = requests.get(url)
            response.raise_for_status()
            jwks = response.json()

            for key in jwks["keys"]:
                if key["kid"] == kid:
                    public_key = RSAAlgorithm.from_jwk(key)
                    AuthService._public_keys_cache[kid] = public_key
                    return public_key

            raise HTTPException(status_code=400, detail="Public key not found in JWKS")

        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Unable to fetch public key: {e!s}")

    @staticmethod
    def decode_jwt_token(token: str) -> dict:
        """Decodes the JWT token using the Auth0 public key.
        
        Supports both Access Tokens and ID Tokens:
        - Access Token: audience = AUTH0_API_IDENTIFIER
        - ID Token: audience = AUTH0_CLIENT_ID
        """
        try:
            unverified_header = jwt.get_unverified_header(token)
            if unverified_header is None or "kid" not in unverified_header:
                raise HTTPException(status_code=400, detail="Missing 'kid' in JWT header")

            public_key = AuthService.get_auth0_public_key(unverified_header["kid"])

            # Failsafe: Strip quotes from the domain to prevent issuer mismatches.
            domain = (settings.AUTH0_DOMAIN or "").strip().strip("'\"")
            issuer = f"https://{domain}/"

            # Build list of trusted audiences (supports both Access Token and ID Token)
            trusted_audiences = []
            if settings.AUTH0_API_IDENTIFIER:
                trusted_audiences.append(settings.AUTH0_API_IDENTIFIER)
            if settings.AUTH0_CLIENT_ID:
                trusted_audiences.extend(settings.AUTH0_CLIENT_ID.split(","))

            decoded_token = jwt.decode(token, public_key, algorithms=settings.AUTH0_ALGORITHMS, audience=trusted_audiences, issuer=issuer)

            return decoded_token

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.exceptions.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid JWT token")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token decoding error: {e!s}")

    @staticmethod
    def get_current_user(token: str) -> dict:
        """Gets the current user data from the decoded token."""
        return AuthService.decode_jwt_token(token)

    @staticmethod
    def check_user_permission(decoded_token: dict, required_permission: str):
        """Checks if the user has the required permission."""
        if "permissions" not in decoded_token:
            raise HTTPException(status_code=403, detail="Permissions not found in token")

        if required_permission not in decoded_token["permissions"]:
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Missing: {required_permission}")

    @staticmethod
    def decode_id_token(id_token: str) -> dict:
        """Decodes the ID token using the Auth0 public key."""
        try:
            unverified_header = jwt.get_unverified_header(id_token)
            if unverified_header is None or "kid" not in unverified_header:
                raise HTTPException(status_code=400, detail="Missing 'kid' in JWT header")

            public_key = AuthService.get_auth0_public_key(unverified_header["kid"])

            # Failsafe: Strip quotes from the domain to prevent issuer mismatches.
            domain = (settings.AUTH0_DOMAIN or "").strip().strip("'\"")
            issuer = f"https://{domain}/"
            trusted_audiences = settings.AUTH0_CLIENT_ID.split(",").copy()


            decoded_id_token = jwt.decode(id_token, public_key, algorithms=settings.AUTH0_ALGORITHMS, audience=trusted_audiences, issuer=issuer)

            return decoded_id_token

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="ID token expired")
        except jwt.exceptions.DecodeError:
            raise HTTPException(status_code=401, detail="Invalid ID token")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"ID token decoding error: {e!s}")
