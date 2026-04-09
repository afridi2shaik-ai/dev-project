import aiohttp
from fastapi import Header, HTTPException, Query, Request, Security, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.db.database import MongoClient, get_database
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_http_client(request: Request) -> aiohttp.ClientSession:
    """Dependency to get the application's aiohttp ClientSession from the app state."""
    return request.app.state.http_client


async def get_http_client_ws(websocket: WebSocket) -> aiohttp.ClientSession:
    """Dependency to get the application's aiohttp ClientSession from the app state for WebSockets."""
    return websocket.app.state.http_client


def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme), x_id_token: str | None = Header(None, description="Auth0 ID Token"), x_tenant_id: str | None = Header(None, description="Tenant ID for M2M flows")) -> dict:
    if not settings.AUTH_ENABLED:
        return {"sub": "test_user", "name": "test_user", "email": "test@test.com", "tenant_id": "6955fc4ca1ff5c9e9141565e825eadb6"}

    access_token: str | None = None
    if credentials:
        access_token = credentials.credentials
    else:
        # If the standard 'Bearer' scheme is not found, check the header manually.
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 1:
                # Case: 'Authorization: <token>'
                access_token = parts[0]
            elif len(parts) == 2 and parts[0].lower() == "bearer":
                # This case is technically handled by HTTPBearer, but we'll include it for robustness.
                access_token = parts[1]

    if not access_token:
        raise HTTPException(status_code=403, detail="Authentication credentials were not provided")

    # Primary authentication is always via the access token
    user_data = AuthService.get_current_user(access_token)

    # If an ID token is also provided, decode it and merge the details
    if x_id_token:
        try:
            id_token_data = AuthService.decode_id_token(x_id_token)
            # Merge details, giving preference to ID token for profile info
            user_data.update(
                {
                    **id_token_data,
                    # Add any other claims from the ID token you need
                }
            )
        except HTTPException as e:
            # If the ID token is invalid, we can decide to fail or just log a warning
            # For now, let's raise an error to be strict.
            raise HTTPException(status_code=400, detail=f"Invalid ID Token: {e.detail}")

    # Fallback: if tenant_id is not in the JWT, use X-Tenant-ID header (M2M flows)
    if "tenant_id" not in user_data:
        if x_tenant_id:
            user_data["tenant_id"] = x_tenant_id
        else:
            raise HTTPException(status_code=403, detail="tenant_id is missing in the token")

    return user_data


async def get_db(current_user: dict = Security(get_current_user)) -> AsyncIOMotorDatabase:
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID not found in token.")

    client = MongoClient.get_client()
    existing_dbs = await client.list_database_names()
    if tenant_id not in existing_dbs:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid tenant.")

    return get_database(tenant_id, client)


async def get_db_from_request(request: Request) -> AsyncIOMotorDatabase:
    tenant_id = request.query_params.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id must be provided as a query parameter.")

    client = MongoClient.get_client()
    existing_dbs = await client.list_database_names()
    if tenant_id not in existing_dbs:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid tenant.")

    return get_database(tenant_id, client)


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number to retrieve."),
        limit: int = Query(10, ge=1, le=200, description="Number of items per page."),
    ):
        self.page = page
        self.limit = limit
        self.skip = (page - 1) * limit
