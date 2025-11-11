"""Configuration management for Authorization API."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/payment_events_db",
        description="PostgreSQL connection string",
    )
    database_pool_min_size: int = Field(default=10, description="Minimum pool size")
    database_pool_max_size: int = Field(default=20, description="Maximum pool size")

    # AWS Configuration
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_endpoint_url: str | None = Field(
        default=None, description="AWS endpoint URL (for LocalStack)"
    )
    aws_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: str | None = Field(default=None, description="AWS secret access key")

    # SQS Queue URLs
    auth_requests_queue_url: str = Field(
        default="http://localhost:4566/000000000000/auth-requests.fifo",
        description="SQS FIFO queue for auth requests",
    )
    void_requests_queue_url: str = Field(
        default="http://localhost:4566/000000000000/void-requests",
        description="SQS queue for void requests",
    )

    # Service Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    environment: str = Field(default="development", description="Environment name")
    service_name: str = Field(default="authorization-api", description="Service name")

    # Outbox Processor
    outbox_processor_enabled: bool = Field(
        default=True, description="Enable outbox processor"
    )
    outbox_processor_interval_ms: int = Field(
        default=100, description="Outbox processor polling interval in milliseconds"
    )
    outbox_processor_batch_size: int = Field(
        default=100, description="Outbox processor batch size"
    )

    # API Configuration
    max_poll_duration_seconds: int = Field(
        default=5, description="Max time to poll for auth response"
    )
    poll_interval_ms: int = Field(
        default=100, description="Poll interval for auth response in milliseconds"
    )


# Global settings instance
settings = Settings()
