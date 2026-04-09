# Authentication & Authorization Guide

## Overview

The Pipecat-Service implements a comprehensive authentication and authorization system using Auth0 for identity management and JWT tokens for secure API access. This guide covers the authentication architecture, token types, authorization patterns, and security best practices.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Authentication Types](#authentication-types)
3. [JWT Token Management](#jwt-token-management)
4. [Authorization Patterns](#authorization-patterns)
5. [Configuration](#configuration)
6. [Security Best Practices](#security-best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Authentication Flow

The authentication system follows an OAuth 2.0 flow with Auth0 as the identity provider:

```
Client Application
    ↓
1. Request Token via /auth/token
    ↓
Pipecat-Service Auth Router
    ↓
2. Validate credentials
    ↓
3. Call Auth0 API (Resource Owner Password Grant)
    ↓
Auth0 Identity Provider
    ↓
4. Return access token + ID token
    ↓
5. Service returns tokens to client
    ↓
Client Application
    ↓ (Stores token)
6. Subsequent API calls with Bearer token
    ↓
Pipecat-Service API Endpoints
    ↓
7. Validate JWT signature and claims
    ↓
8. Extract tenant_id and user info
    ↓
9. Return response (or 403 if invalid)
```

### Multi-Tenancy Model

**Key Concept:** Each tenant has its own:
- MongoDB database
- Organization ID (Auth0)
- API credentials and configurations
- Call history and customer profiles

**Tenant Identification:**
- Derived from JWT `tenant_id` claim
- Used to route requests to correct database
- Ensures complete data isolation

---

## Authentication Types

### 1. User Authentication (Password Grant)

**Purpose:** Allow end users to get access tokens using their username/password.

**Endpoint:** `POST /auth/token`

**Request:**
```json
{
    "username": "user@example.com",
    "password": "password123",
    "org_id": "optional-auth0-org-id"
}
```

**Response:**
```json
{
    "access_token": "eyJhbGc...",
    "id_token": "eyJhbGc...",
    "token_type": "Bearer",
    "expires_in": 86400
}
```

**Usage:**
```python
# Client side
response = await httpx.post(
    "http://localhost:7860/auth/token",
    json={
        "username": "user@example.com",
        "password": "password",
    }
)
token = response.json()["access_token"]

# Use in subsequent requests
headers = {"Authorization": f"Bearer {token}"}
```

**Implementation:**
- File: `src/app/api/auth/router.py`
- Service: `src/app/services/auth_service.py`
- Auth0 Flow: Resource Owner Password Grant

### 2. Tenant Token Authentication

**Purpose:** Generate tokens for a tenant directly (admin use case).

**Service:** `TenantTokenService`

**When to use:**
- Automated systems (cron jobs, webhooks)
- Admin operations
- Service-to-service calls

**Implementation:**
```python
from app.services.tenant_token_service import TenantTokenService

# Generate token for tenant
token_response = await TenantTokenService.generate_tokens(
    username="admin@example.com",
    password="admin_password",
    tenant_id="tenant_123"
)

access_token = token_response.access_token
```

**Error Handling:**
```python
from app.services.tenant_token_service import (
    TenantTokenConfigError,      # Configuration missing
    TenantTokenLookupError,       # Tenant not found
    TenantTokenNotFoundError,     # Organization not found
    TenantTokenAuthError,         # Invalid credentials
    TenantTokenServiceError,      # Other errors
)

try:
    token = await TenantTokenService.generate_tokens(...)
except TenantTokenConfigError as e:
    # Handle configuration issues
    logger.error(f"Auth0 not configured: {e}")
except TenantTokenNotFoundError as e:
    # Handle missing organization
    logger.error(f"Tenant not found: {e}")
except TenantTokenAuthError as e:
    # Handle invalid credentials
    logger.error(f"Invalid credentials: {e}")
```

### 3. Guest/Anonymous Mode

**When enabled:**
- `AUTH_ENABLED=false` in environment
- No authentication required
- All requests use test credentials

**Test User (when auth disabled):**
```python
{
    "sub": "test_user",
    "name": "test_user",
    "email": "test@test.com",
    "tenant_id": "6955fc4ca1ff5c9e9141565e825eadb6"
}
```

**Use Case:**
- Development and testing
- Demos
- Internal tools

---

## JWT Token Management

### Token Structure

**JWT Format:** `header.payload.signature`

**Header:**
```json
{
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-id"
}
```

**Payload (Access Token):**
```json
{
    "iss": "https://your-domain.auth0.com/",
    "sub": "user123",
    "aud": "https://your-api-identifier",
    "exp": 1704067200,
    "iat": 1704052800,
    "email": "user@example.com",
    "email_verified": true,
    "tenant_id": "tenant_123",
    "org_id": "org123",
    "aud": "https://your-api"
}
```

**Payload (ID Token):**
```json
{
    "iss": "https://your-domain.auth0.com/",
    "sub": "user123",
    "aud": "your-app-client-id",
    "exp": 1704067200,
    "iat": 1704052800,
    "email": "user@example.com",
    "name": "User Name",
    "picture": "https://...",
    "email_verified": true
}
```

**Key Claims:**
- `sub` - Subject (unique user identifier)
- `email` - User email
- `email_verified` - Whether email is verified
- `name` - User's full name
- `tenant_id` - **Critical:** Which database to use
- `org_id` - Auth0 organization
- `exp` - Expiration timestamp
- `iat` - Issued at timestamp

### Token Validation

**Implementation:**
```python
# File: src/app/services/auth_service.py

class AuthService:
    @staticmethod
    def decode_jwt_token(token: str) -> dict:
        """Decodes and validates JWT token."""
        
        # 1. Get JWT header to find key ID (kid)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        # 2. Fetch Auth0 public key using kid
        public_key = AuthService.get_auth0_public_key(kid)
        
        # 3. Verify signature and decode
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.AUTH0_API_IDENTIFIER,
        )
        
        return decoded
```

**Validation Steps:**
1. ✅ Verify JWT signature (ensures not tampered with)
2. ✅ Check expiration (exp claim)
3. ✅ Verify issuer (iss claim)
4. ✅ Verify audience (aud claim)
5. ✅ Extract claims (tenant_id, user info)

### Token Caching

**Key Caching:**
```python
class AuthService:
    _public_keys_cache: ClassVar[dict] = {}
    
    @staticmethod
    def get_auth0_public_key(kid: str):
        # Check cache first
        if kid in AuthService._public_keys_cache:
            return AuthService._public_keys_cache[kid]
        
        # Fetch from Auth0 if not cached
        # ... fetch and cache
```

**Benefits:**
- Reduces Auth0 API calls
- Faster token validation
- Lower latency for API requests

**Invalidation:**
- Keys cached indefinitely (Auth0 recommends this)
- Trust Auth0's rotation mechanism

---

## Authorization Patterns

### Dependency-Based Authorization

**File:** `src/app/api/dependencies.py`

**Pattern:** Use FastAPI Security dependencies to enforce auth

```python
from fastapi import Security, HTTPException

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_id_token: str | None = Header(None)
) -> dict:
    """Extract and validate current user from JWT."""
    
    if not settings.AUTH_ENABLED:
        return {"sub": "test_user", "tenant_id": "test_tenant"}
    
    # Extract token from Bearer header
    access_token = credentials.credentials if credentials else None
    
    # Validate token
    user_data = AuthService.get_current_user(access_token)
    
    # Merge ID token if provided
    if x_id_token:
        id_token_data = AuthService.decode_id_token(x_id_token)
        user_data.update(id_token_data)
    
    return user_data
```

**Usage in Endpoints:**
```python
from fastapi import APIRouter, Security

router = APIRouter()

@router.get("/profile")
async def get_profile(
    current_user: dict = Security(get_current_user)
) -> dict:
    """Returns current user's profile."""
    return {
        "name": current_user["name"],
        "email": current_user["email"],
        "tenant_id": current_user["tenant_id"]
    }
```

### Tenant Isolation

**Pattern:** Route to correct database based on tenant_id

```python
async def get_db(
    current_user: dict = Security(get_current_user)
) -> AsyncIOMotorDatabase:
    """Get database for authenticated tenant."""
    
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")
    
    client = MongoClient.get_client()
    
    # Verify tenant database exists
    existing_dbs = await client.list_database_names()
    if tenant_id not in existing_dbs:
        raise HTTPException(status_code=403, detail="Tenant not found")
    
    # Return tenant-specific database
    return get_database(tenant_id, client)
```

**Usage in Endpoints:**
```python
@router.get("/sessions")
async def list_sessions(
    db: AsyncIOMotorDatabase = Security(get_db),
    current_user: dict = Security(get_current_user)
) -> dict:
    """List sessions for authenticated tenant."""
    
    # db is already tenant-specific
    sessions_collection = db["sessions"]
    sessions = await sessions_collection.find({}).to_list(length=100)
    
    return {"sessions": sessions}
```

### Role-Based Access Control (RBAC)

**Future Pattern:** Can extend with Auth0 roles

```python
async def require_admin(
    current_user: dict = Security(get_current_user)
) -> dict:
    """Require user to have admin role."""
    
    roles = current_user.get("roles", [])
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")
    
    return current_user
```

**Usage:**
```python
@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: str,
    admin_user: dict = Security(require_admin)
) -> dict:
    """Only admins can delete organizations."""
    ...
```

---

## Configuration

### Environment Variables

**File:** `.env` or environment config

**Auth0 Configuration:**
```bash
# Enable/disable authentication
AUTH_ENABLED=true

# Auth0 settings
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_API_IDENTIFIER=https://your-api
AUTH0_M2M_CLIENT_ID=your-m2m-client-id
AUTH0_M2M_CLIENT_SECRET=your-m2m-client-secret

# For tenant token generation
AUTH_USERNAME=admin@example.com
AUTH_PASSWORD=admin_password
```

**Settings Class:**
```python
# File: src/app/core/config.py

class Settings(BaseSettings):
    # Authentication
    AUTH_ENABLED: bool = True
    AUTH0_DOMAIN: str | None = None
    AUTH0_API_IDENTIFIER: str | None = None
    AUTH0_M2M_CLIENT_ID: str | None = None
    AUTH0_M2M_CLIENT_SECRET: str | None = None
    AUTH_USERNAME: str | None = None
    AUTH_PASSWORD: str | None = None
```

### Enabling/Disabling Auth

**Disable Auth (Development):**
```bash
AUTH_ENABLED=false
```

**Enable Auth (Production):**
```bash
AUTH_ENABLED=true
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_API_IDENTIFIER=https://your-api-identifier
AUTH0_M2M_CLIENT_ID=xxx
AUTH0_M2M_CLIENT_SECRET=xxx
```

---

## Security Best Practices

### 1. Token Handling

✅ **DO:**
- Store tokens in secure HTTP-only cookies (web clients)
- Use HTTPS only in production
- Verify token signature before use
- Respect token expiration (exp claim)
- Refresh tokens before expiry

❌ **DON'T:**
- Store tokens in localStorage (vulnerable to XSS)
- Log full tokens in production
- Share tokens across users
- Use expired tokens
- Transmit tokens over HTTP

### 2. API Key Management

**For API Credentials (in business tools):**
- Store API keys encrypted in MongoDB
- Use `EncryptionService` for encryption
- Never log or expose API keys
- Rotate keys periodically
- Use least-privilege scopes

```python
from app.services.encryption_service import EncryptionService

# Encrypt API key
encryption_service = EncryptionService()
encrypted_key = encryption_service.encrypt(api_key)

# Store in database
await credentials_collection.insert_one({
    "provider": "stripe",
    "api_key": encrypted_key  # Stored encrypted
})

# Decrypt when needed
decrypted_key = encryption_service.decrypt(encrypted_key)
```

### 3. Authorization Checks

**Always verify:**
- ✅ User is authenticated (not expired)
- ✅ Tenant matches database access
- ✅ User has required role (if RBAC)
- ✅ Resource belongs to user's tenant

**Example Safe Endpoint:**
```python
@router.get("/organizations/{org_id}")
async def get_organization(
    org_id: str,
    current_user: dict = Security(get_current_user),
    db: AsyncIOMotorDatabase = Security(get_db)
) -> dict:
    """Get organization details."""
    
    # 1. Verify authenticated
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # 2. Get organization
    org = await db["organizations"].find_one({"_id": org_id})
    
    # 3. Verify tenant owns organization
    if org["tenant_id"] != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return org
```

### 4. Rate Limiting

**Recommended pattern:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/token")
@limiter.limit("5/minute")  # Max 5 token requests per minute
async def get_token(request: Request, data: TokenRequest):
    """Rate-limited token endpoint."""
    ...
```

### 5. CORS Configuration

**Current Config:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production Recommendation:**
```bash
# In .env
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Not: http://*, *, or broad wildcards
```

### 6. HTTPS Enforcement

**Development:**
```
http://localhost:7860  # OK
```

**Production:**
```
https://api.yourdomain.com  # REQUIRED
```

---

## Troubleshooting

### Common Authentication Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `403 - Authentication credentials not provided` | No Bearer token | Add Authorization header |
| `401 - Invalid JWT signature` | Token tampered with | Regenerate token from Auth0 |
| `401 - Token expired` | Token past expiration | Request new token |
| `403 - Invalid tenant` | Tenant DB doesn't exist | Check tenant_id in token |
| `500 - Auth0 not configured` | Missing env variables | Configure AUTH0_* env vars |

### Debug Logging

**Enable detailed auth logging:**
```python
# In dependencies.py or auth_service.py
logger.debug(f"Token payload: {decoded_token}")
logger.debug(f"Current user: {user_data}")
logger.debug(f"Tenant ID: {tenant_id}")
```

### Testing Authentication

**Test with disabled auth:**
```bash
AUTH_ENABLED=false
```

**Test with valid token:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
     http://localhost:7860/api/sessions
```

**Decode JWT (check claims):**
```python
import jwt

token = "your_token_here"
decoded = jwt.decode(token, options={"verify_signature": False})
print(decoded)
```

**Get token from Auth0 (CLI):**
```bash
curl --request POST \
  --url https://${AUTH0_DOMAIN}/oauth/token \
  --header 'content-type: application/json' \
  --data "{
    \"client_id\":\"${AUTH0_M2M_CLIENT_ID}\",
    \"client_secret\":\"${AUTH0_M2M_CLIENT_SECRET}\",
    \"audience\":\"${AUTH0_API_IDENTIFIER}\",
    \"grant_type\":\"client_credentials\"
  }"
```

---

## Summary

The authentication and authorization system provides:

- **Auth0 Integration** - Industry-standard OAuth 2.0 identity provider
- **JWT Tokens** - Secure, stateless authentication
- **Multi-tenancy** - Complete data isolation per tenant
- **Flexible Auth** - Can be disabled for development
- **Security-first** - Signature verification, token caching, secure storage

Use this system to:
1. Authenticate users via password grant
2. Generate tenant tokens for automation
3. Enforce authorization in endpoints
4. Isolate multi-tenant data
5. Implement role-based access control (future)

Always follow security best practices for token handling and authorization checks.

