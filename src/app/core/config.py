import os
from enum import Enum

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    APP_NAME: str = "VAgent"
    AGENT_TYPE: str = os.getenv("AGENT_TYPE", "vagent_pipe_cat")

    # --- AWS Credential Helper Methods ---
    def has_explicit_aws_credentials(self) -> bool:
        """Check if explicit AWS credentials are configured.
        
        Returns True if both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set.
        When False, boto3 will auto-discover credentials from:
        - IAM role (IRSA on EKS)
        - EC2 instance profile
        - Environment variables set by AWS SDK
        - AWS credentials file (~/.aws/credentials)
        """
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    def get_aws_client_kwargs(self) -> dict:
        """Get AWS client kwargs for boto3.
        
        Returns a dict with explicit credentials if configured,
        or an empty dict to let boto3 auto-discover credentials
        from IAM role (IRSA/instance profile).
        
        Usage:
            s3 = boto3.client("s3", region_name=settings.AWS_REGION, **settings.get_aws_client_kwargs())
        """
        if self.has_explicit_aws_credentials():
            return {
                "aws_access_key_id": self.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": self.AWS_SECRET_ACCESS_KEY,
            }
        return {}

    # Logging configuration
    LOG_LEVEL: LogLevel = LogLevel.INFO
    LOGURU_JSON_LOGS: bool = False

    # OpenTelemetry configuration
    OTEL_SERVICE_NAME: str = "pipecat-demo"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_DEBUG_LOG_SPANS: bool = False

    # CORS configuration
    ALLOWED_ORIGINS: str = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:7860,http://localhost:8000").split(",")]

    # Server configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 7860

    # Pipecat services API keys
    DEEPGRAM_API_KEY: str | None = os.getenv("DEEPGRAM_API_KEY")
    ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    SARVAM_API_KEY: str | None = os.getenv("SARVAM_API_KEY")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    CARTESIA_API_KEY: str | None = os.getenv("CARTESIA_API_KEY")
    SONIOX_API_KEY: str | None = os.getenv("SONIOX_API_KEY")
    # Azure Speech
    AZURE_SPEECH_API_KEY: str | None = os.getenv("AZURE_SPEECH_API_KEY")
    AZURE_SPEECH_REGION: str | None = os.getenv("AZURE_SPEECH_REGION")
    # Google Cloud credentials
    GOOGLE_APPLICATION_CREDENTIALS: str | None = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Audio Processing - Krisp SDK
    KRISP_SDK_WHEEL_PATH: str | None = os.getenv("KRISP_SDK_WHEEL_PATH")
    KRISP_VIVA_MODEL_PATH: str | None = os.getenv("KRISP_VIVA_MODEL_PATH", "Krisp/krisp-viva-models-9.9/krisp-viva-pro-v1.kef")

    # Plivo credentials
    PLIVO_AUTH_ID: str | None = os.getenv("PLIVO_AUTH_ID")
    PLIVO_AUTH_TOKEN: str | None = os.getenv("PLIVO_AUTH_TOKEN")
    PLIVO_PHONE_NUMBER: str | None = os.getenv("PLIVO_PHONE_NUMBER")

    # Twilio credentials
    TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER: str | None = os.getenv("TWILIO_PHONE_NUMBER")

    # AWS S3 configuration
    S3_BUCKET_NAME: str | None = os.getenv("S3_BUCKET_NAME")
    AWS_ACCESS_KEY_ID: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str | None = os.getenv("AWS_REGION")
    # Storage configuration
    SAVE_TO_LOCAL: bool = os.getenv("SAVE_TO_LOCAL", True)
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    # MongoDB configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_GLOBAL_DB: str = os.getenv("MONGO_GLOBAL_DB", "global")

    # Auth0 configuration
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", False)
    AUTH0_DOMAIN: str | None = os.getenv("AUTH0_DOMAIN")
    AUTH0_API_IDENTIFIER: str | None = os.getenv("AUTH0_API_IDENTIFIER")
    AUTH0_CLIENT_ID: str | None = os.getenv("AUTH0_CLIENT_ID")
    AUTH0_M2M_CLIENT_ID: str | None = os.getenv("AUTH0_M2M_CLIENT_ID")
    AUTH0_M2M_CLIENT_SECRET: str | None = os.getenv("AUTH0_M2M_CLIENT_SECRET")
    AUTH0_ALGORITHMS: list[str] = ["RS256"]
    JWT_SECRET_KEY: str | None = os.getenv("JWT_SECRET_KEY", "a_secure_secret_key_for_hs256")

    # Encryption key for sensitive data
    ENCRYPTION_KEY: str | None = os.getenv("ENCRYPTION_KEY")

    # External Assistant API configuration
    ASSISTANT_API_BASE_URL: str | None = os.getenv("ASSISTANT_API_BASE_URL")
    ASSISTANT_API_TIMEOUT: int = int(os.getenv("ASSISTANT_API_TIMEOUT", 5))
    ASSISTANT_API_RETRY_ATTEMPTS: int = int(os.getenv("ASSISTANT_API_RETRY_ATTEMPTS", 3))

    # Callback Scheduler configuration
    # TODO: When ready to use the actual callback scheduler API, update this base URL:
    #   - Current: Points to dummy endpoint for testing (http://localhost:7860/vagent/api/dummy)
    #   - Production: Set CALLBACK_SCHEDULER_BASE_URL env var to your actual scheduler API base URL
    #   - Example: "https://scheduler-api.example.com" or "http://scheduler-service:8000"
    #   - The client will append "/callbacks/schedule" to this base URL
    CALLBACK_SCHEDULER_BASE_URL: str = os.getenv("CALLBACK_SCHEDULER_BASE_URL", "http://localhost:7860/vagent/api/dummy")
    CALLBACK_SCHEDULER_TIMEOUT_SECS: int = int(os.getenv("CALLBACK_SCHEDULER_TIMEOUT_SECS", 30))

    LITELLM_API_KEY: str | None = os.getenv("LITELLM_API_KEY")
    LITELLM_BASE_URL: str | None = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
    
    # Service account credentials for on-behalf token generation (no tenant in env)
    AUTH_USERNAME: str | None = os.getenv("AUTH_USERNAME")
    AUTH_PASSWORD: str | None = os.getenv("AUTH_PASSWORD")
    RAG_API_URL: str | None = os.getenv("RAG_API_URL")

    EVENTMANAGER_API_URL: str | None = os.getenv("EVENTMANAGER_API_URL")
    EVENTMANAGER_ENABLED: bool = os.getenv("EVENTMANAGER_ENABLED", "False")

    # CRM API base when tools.crm.enabled (no trailing slash), e.g. https://host/crm-api — Pipecat appends /mcp/stream
    CRM_MCP_URL: str | None = os.getenv("CRM_MCP_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def check_s3_config(self) -> "Settings":
        """Validate S3 configuration.
        
        AWS_REGION is always required for S3 operations.
        AWS credentials (ACCESS_KEY_ID + SECRET_ACCESS_KEY) are optional:
        - If provided: boto3 uses explicit credentials
        - If not provided: boto3 auto-discovers from IAM role (IRSA/instance profile)
        
        This enables production deployments on EKS with IRSA without code changes.
        """
        if not self.SAVE_TO_LOCAL and self.S3_BUCKET_NAME:
            if not self.AWS_REGION:
                raise ValueError("AWS_REGION must be set in your .env file when using S3 storage.")
            # Note: AWS credentials are optional - boto3 can auto-discover from IAM role
            # Log a helpful message about credential discovery
            if not self.has_explicit_aws_credentials():
                # This is INFO level - it's expected in production with IRSA
                import logging
                logging.getLogger(__name__).info(
                    "AWS credentials not explicitly configured. "
                    "Boto3 will auto-discover from IAM role (IRSA/instance profile)."
                )
        return self


settings = Settings()
