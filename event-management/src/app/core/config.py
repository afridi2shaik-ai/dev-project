import logging
import os

import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# Auth0 configuration (RAG-style)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
API_IDENTIFIER_FRONT_END = os.getenv("API_IDENTIFIER_FRONT_END")
ALGORITHM = os.getenv("ALGORITHM", "RS256")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# CORS configuration
_raw_cors = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [origin.strip() for origin in _raw_cors.split(",") if origin.strip()]

# Circuitry: parse "email,password" or "email,password,tenant_id" from single env
_raw_creds = os.getenv("CIRCUITRY_CREDENTIALS", "")
if _raw_creds and "," in _raw_creds:
    _parts = _raw_creds.split(",", 2)
    CIRCUITRY_EMAIL = _parts[0].strip()
    CIRCUITRY_PASSWORD = _parts[1].strip()
else:
    CIRCUITRY_EMAIL = None
    CIRCUITRY_PASSWORD = None

# Circuitry API base URL (e.g. https://dev.circuitry.ai/api); token and usage paths are appended.
CIRCUITRY_API_BASE_URL = (os.getenv("CIRCUITRY_API_BASE_URL") or "https://dev.circuitry.ai/api").strip().rstrip("/")

# Pipecat credential name used to get-or-create Circuitry auth credential (list/create by this name).
CIRCUITRY_CREDENTIAL_NAME = (os.getenv("CIRCUITRY_CREDENTIAL_NAME") or "circuitry_ai_dev").strip()

# Pipecat service base URL (e.g. https://dev.vagent.circuitry.ai); used for business-tools API.
PIPECAT_BASE_URL = (os.getenv("PIPECAT_BASE_URL") or "").strip().rstrip("/") or None

# Backend assistant/agent config API base URL (e.g. https://dev.vagent.circuitry.ai/agentconfig); used for GET/PATCH agent.
BACKEND_ASSISTANT_API_BASE_URL = (os.getenv("BACKEND_ASSISTANT_API_BASE_URL") or "").strip().rstrip("/") or None

# Circuitry business tool (advisor) dialogue API base URL (e.g. https://dev.dialogue.circuitry.ai); used in advisor tool api_config.base_url.
URL_CIRCUITRY_BUSINESS_TOOL = (os.getenv("URL_CIRCUITRY_BUSINESS_TOOL") or "https://dev.dialogue.circuitry.ai").strip().rstrip("/")

# When True, log full request/response payloads for ingest and Circuitry. Set ADVANCE_LOGS=true to enable.
ADVANCE_LOGS = os.getenv("ADVANCE_LOGS", "false").strip().lower() in {"1", "true", "yes", "on"}
