"""Test Payment Token Service client configuration and initialization."""

import pytest

from auth_processor_worker.clients.payment_token_client import PaymentTokenServiceClient
from auth_processor_worker.config import settings


class TestPaymentTokenServiceClientConfiguration:
    """Test suite for Payment Token Service client configuration."""

    def test_client_from_settings(self):
        """Test that client can be created from application settings."""
        # Create client using settings from .env
        client = PaymentTokenServiceClient(
            base_url=settings.payment_token_service.base_url,
            service_auth_token=settings.payment_token_service.service_auth_token,
            timeout_seconds=settings.payment_token_service.timeout_seconds,
        )

        # Verify client is properly configured
        assert client.base_url == settings.payment_token_service.base_url.rstrip("/")
        assert client.service_auth_token == settings.payment_token_service.service_auth_token
        assert client.timeout_seconds == settings.payment_token_service.timeout_seconds
        assert client.http_client is not None

    def test_client_initialization_with_custom_values(self):
        """Test client initialization with custom values."""
        client = PaymentTokenServiceClient(
            base_url="https://custom-service.example.com",
            service_auth_token="custom-token",
            timeout_seconds=10.0,
        )

        assert client.base_url == "https://custom-service.example.com"
        assert client.service_auth_token == "custom-token"
        assert client.timeout_seconds == 10.0

    def test_client_base_url_normalization(self):
        """Test that base URL trailing slashes are handled correctly."""
        # With trailing slash
        client1 = PaymentTokenServiceClient(
            base_url="http://localhost:8000/",
            service_auth_token="token",
            timeout_seconds=5.0,
        )
        assert client1.base_url == "http://localhost:8000"

        # Without trailing slash
        client2 = PaymentTokenServiceClient(
            base_url="http://localhost:8000",
            service_auth_token="token",
            timeout_seconds=5.0,
        )
        assert client2.base_url == "http://localhost:8000"

    def test_settings_configuration_values(self):
        """Test that settings are loaded correctly from environment."""
        # Verify settings match .env file values
        assert settings.payment_token_service.base_url is not None
        assert settings.payment_token_service.service_auth_token is not None
        assert settings.payment_token_service.timeout_seconds > 0
        assert isinstance(settings.payment_token_service.timeout_seconds, int)

        # Verify default values or environment values
        assert settings.payment_token_service.max_retries >= 0

    @pytest.mark.asyncio
    async def test_client_cleanup(self):
        """Test that client properly cleans up resources."""
        client = PaymentTokenServiceClient(
            base_url="http://localhost:8000",
            service_auth_token="test-token",
            timeout_seconds=5.0,
        )

        # Close should not raise any errors
        await client.close()

    @pytest.mark.asyncio
    async def test_client_context_manager_cleanup(self):
        """Test that client properly cleans up when used as context manager."""
        # Using context manager should properly initialize and cleanup
        async with PaymentTokenServiceClient(
            base_url="http://localhost:8000",
            service_auth_token="test-token",
            timeout_seconds=5.0,
        ) as client:
            assert client.http_client is not None

        # After context exit, client should be closed
        # (We can't easily verify this without implementation details)
