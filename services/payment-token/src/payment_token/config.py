"""Configuration management for Payment Token Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/payment_tokens"

    # Application
    debug: bool = False
    environment: str = "development"

    # Token settings
    default_token_ttl_hours: int = 24

    # AWS KMS
    bdk_kms_key_id: str = ""
    current_key_version: str = "v1"
    aws_region: str = "us-east-1"

    # For testing with LocalStack
    kms_endpoint_url: str | None = None

    # Internal API authentication
    allowed_services: list[str] = ["auth-processor-worker", "void-processor-worker"]
    internal_api_require_mtls: bool = False  # Set to True in production

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance
settings = Settings()
