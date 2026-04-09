import logging
from typing import ClassVar

import jwt
import requests
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from app.core.config import ALGORITHM, API_IDENTIFIER_FRONT_END, AUTH0_DOMAIN, CLIENT_ID

logger = logging.getLogger(__name__)


class AuthService:
    _public_keys_cache: ClassVar[dict[str, object]] = {}

    @staticmethod
    def _get_public_key(kid: str):
        if kid in AuthService._public_keys_cache:
            return AuthService._public_keys_cache[kid]

        domain = (AUTH0_DOMAIN or "").strip().strip("'\"")
        if not domain:
            raise HTTPException(status_code=500, detail="AUTH0_DOMAIN is not configured")

        try:
            url = f"https://{domain}/.well-known/jwks.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            jwks = response.json()
        except requests.exceptions.RequestException as exc:
            raise HTTPException(status_code=500, detail=f"Unable to fetch JWKS: {exc!s}") from exc

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                public_key = RSAAlgorithm.from_jwk(key)
                AuthService._public_keys_cache[kid] = public_key
                return public_key

        raise HTTPException(status_code=401, detail="Public key not found in JWKS")

    @staticmethod
    def decode_id_token(id_token: str) -> dict:
        try:
            unverified_header = jwt.get_unverified_header(id_token)
            if not unverified_header or "kid" not in unverified_header:
                raise HTTPException(status_code=401, detail="Missing 'kid' in token header")

            public_key = AuthService._get_public_key(unverified_header["kid"])
            domain = (AUTH0_DOMAIN or "").strip().strip("'\"")
            issuer = f"https://{domain}/"

            audiences: list[str] = []
            if CLIENT_ID:
                audiences.extend([v.strip() for v in CLIENT_ID.split(",") if v.strip()])
            if API_IDENTIFIER_FRONT_END:
                audiences.extend([v.strip() for v in API_IDENTIFIER_FRONT_END.split(",") if v.strip()])
            if not audiences:
                raise HTTPException(status_code=500, detail="CLIENT_ID/API_IDENTIFIER_FRONT_END not configured")

            return jwt.decode(
                id_token,
                public_key,
                algorithms=[ALGORITHM],
                audience=audiences,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="ID token expired") from exc
        except jwt.exceptions.DecodeError as exc:
            raise HTTPException(status_code=401, detail="Invalid ID token") from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=f"ID token verification failed: {exc!s}") from exc
