import logging

import requests

from ...core.config import (
    CIRCUITRY_API_BASE_URL,
    CIRCUITRY_EMAIL,
    CIRCUITRY_PASSWORD,
)

logger = logging.getLogger(__name__)

CIRCUITRY_TOKEN_URL = f"{CIRCUITRY_API_BASE_URL}/v3/data/token"


def get_circuitry_token(tenant_id: str | None = None) -> str | None:
    """
    Call Circuitry token API. Uses tenant_id from ingest when provided.
    Returns the access token or None.
    """
    if not CIRCUITRY_EMAIL or not CIRCUITRY_PASSWORD:
        logger.warning("Circuitry token: CIRCUITRY_CREDENTIALS not set or invalid (need email,password)")
        return None
    payload = {
        "email": CIRCUITRY_EMAIL,
        "password": CIRCUITRY_PASSWORD,
    }
    tid = tenant_id
    if tid:
        payload["tenant_id"] = tid
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer null",
    }
    try:
        resp = requests.post(
            CIRCUITRY_TOKEN_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token and isinstance(data.get("data"), dict):
            inner = data["data"]
            token = inner.get("token") or inner.get("access_token") or inner.get("accessToken") or inner.get("jwt")
        if token:
            return token
        logger.warning(
            "Circuitry token: response missing 'token' or 'access_token', keys=%s",
            list(data.keys()),
        )
        return None
    except requests.RequestException as e:
        logger.warning("Circuitry token request failed: %s", e)
        return None
