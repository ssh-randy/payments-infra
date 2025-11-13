"""Configuration management for Auth Processor Worker Service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Worker-specific settings for SQS processing."""

    sqs_queue_url: str = Field(
        default="",
        description="SQS FIFO queue URL for auth requests"
    )
    batch_size: int = Field(default=1, description="Number of messages to fetch per batch")
    wait_time_seconds: int = Field(default=20, description="Long polling wait time")
    visibility_timeout: int = Field(default=30, description="Message visibility timeout in seconds")
    max_retries: int = Field(default=5, description="Maximum retry attempts")
    lock_ttl_seconds: int = Field(default=30, description="Distributed lock TTL")
    worker_id: str = Field(default="worker-1", description="Unique worker identifier")


class PaymentTokenServiceSettings(BaseSettings):
    """Payment Token Service client settings."""

    base_url: str = Field(
        default="http://localhost:8000",
        description="Payment Token Service base URL"
    )
    service_auth_token: str = Field(
        default="dev-auth-token",
        description="Service authentication token"
    )
    timeout_seconds: int = Field(default=5, description="Request timeout")
    max_retries: int = Field(default=2, description="Maximum retry attempts")


class StripeProcessorSettings(BaseSettings):
    """Stripe processor settings."""

    api_key: str = Field(default="", description="Stripe API key")
    timeout_seconds: int = Field(default=10, description="Request timeout")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/payment_events",
        description="PostgreSQL connection string"
    )

    # Application
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")

    # AWS
    aws_region: str = Field(default="us-east-1", description="AWS region")
    aws_endpoint_url: str | None = Field(default=None, description="AWS endpoint (for LocalStack)")

    # Worker settings
    worker: WorkerSettings = Field(default_factory=WorkerSettings)

    # Payment Token Service
    payment_token_service: PaymentTokenServiceSettings = Field(
        default_factory=PaymentTokenServiceSettings
    )

    # Stripe Processor
    stripe: StripeProcessorSettings = Field(default_factory=StripeProcessorSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
    )


# Global settings instance
settings = Settings()
