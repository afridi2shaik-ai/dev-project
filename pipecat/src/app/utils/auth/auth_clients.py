"""Auth0 client classes for token generation."""

import json

import jwt as pyjwt
import requests
from loguru import logger


def _safe_decode_jwt_claims(token: str) -> dict | None:
    """Decode a JWT without signature verification to inspect claims."""
    try:
        return pyjwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None


class Auth0PasswordGrantClient:
    """A client for generating Auth0 access tokens using the Resource Owner Password Grant."""

    def __init__(self, domain: str):
        self.token_url = f"https://{domain}/oauth/token"
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        # This realm corresponds to the name of your Auth0 Database Connection
        self.realm = "Username-Password-Authentication"

    def get_token(self, *, client_id: str, client_secret: str, audience: str, username: str, password: str, org_id: str, scope: str = "openid profile email"):
        """Generates an access token for a user using the Resource Owner Password Grant.
        Reference: https://auth0.com/docs/api/authentication/resource-owner-password-flow/get-token
        """
        payload = {
            # This specific grant type allows specifying a database connection (realm)
            "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
            "username": username,
            "password": password,
            "realm": self.realm,
            "org_id": org_id,
            "scope": scope,
        }

        # Log request parameters (mask secrets)
        safe_payload = {
            "grant_type": payload["grant_type"],
            "client_id": client_id,
            "audience": audience,
            "username": username,
            "realm": self.realm,
            "org_id": org_id,
            "scope": scope,
        }
        logger.info(f"🔑 Auth0 token request: POST {self.token_url} | params: {json.dumps(safe_payload)}")

        try:
            response = requests.post(self.token_url, data=payload, headers=self.headers)
            status_code = response.status_code

            if status_code != 200:
                logger.error(
                    f"🔑 Auth0 token response: status={status_code} | "
                    f"body={response.text} | org_id={org_id} username={username}"
                )
                response.raise_for_status()

            token_data = response.json()

            # Log response metadata and inspect JWT claims
            access_claims = _safe_decode_jwt_claims(token_data.get("access_token", ""))
            id_claims = _safe_decode_jwt_claims(token_data.get("id_token", ""))

            logger.info(
                f"🔑 Auth0 token response: status={status_code} | "
                f"expires_in={token_data.get('expires_in')} | "
                f"access_token claims: {list(access_claims.keys()) if access_claims else 'DECODE_FAILED'} | "
                f"access_token has tenant_id: {'tenant_id' in access_claims if access_claims else False} | "
                f"access_token org_id: {access_claims.get('org_id', 'MISSING') if access_claims else 'DECODE_FAILED'} | "
                f"id_token claims: {list(id_claims.keys()) if id_claims else 'DECODE_FAILED'} | "
                f"id_token has tenant_id: {'tenant_id' in id_claims if id_claims else False}"
            )

            if access_claims and "tenant_id" not in access_claims:
                logger.warning(
                    f"⚠️ Auth0 access_token is MISSING tenant_id claim! "
                    f"org_id={org_id} username={username} "
                    f"Available claims: {list(access_claims.keys())}"
                )

            return token_data
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while getting user token: {http_err} - {response.text}")
            raise
        except Exception as err:
            logger.error(f"An unexpected error occurred while getting user token: {err}")
            raise


class Auth0M2MClient:
    """A client for generating Auth0 access tokens using the Client Credentials Grant for M2M."""

    def __init__(self, domain: str):
        self.token_url = f"https://{domain}/oauth/token"
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def get_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        audience: str,
    ):
        """Generates an access token for a machine-to-machine application.
        Reference: https://auth0.com/docs/api/authentication/client-credentials-flow/get-token
        """
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        }

        try:
            logger.info(f"Requesting M2M token from {self.token_url} for audience {audience}")
            response = requests.post(self.token_url, data=payload, headers=self.headers)
            response.raise_for_status()
            logger.info("Successfully generated M2M token.")
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while getting M2M token: {http_err} - {response.text}")
            raise
        except Exception as err:
            logger.error(f"An unexpected error occurred while getting M2M token: {err}")
            raise
