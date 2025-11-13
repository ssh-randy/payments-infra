"""Payment Token Service mock fixtures for integration testing.

These fixtures mock the PaymentTokenServiceClient to avoid calling the real
Payment Token Service during integration tests. This allows testing the worker
in isolation while simulating various token service scenarios.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

# Add shared proto directory to Python path
_shared_proto_path = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import payment_token_pb2

from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)


class MockPaymentTokenServiceClient:
    """
    Mock implementation of PaymentTokenServiceClient for testing.

    This mock allows tests to control the behavior of token decryption
    by configuring responses for specific payment tokens or restaurants.
    """

    def __init__(self, base_url: str, service_auth_token: str, timeout_seconds: float = 5.0):
        """Initialize the mock client (matches real client signature)."""
        self.base_url = base_url
        self.service_auth_token = service_auth_token
        self.timeout_seconds = timeout_seconds

        # Configuration for mock behavior
        self.token_responses: dict[str, Any] = {}
        self.default_response: payment_token_pb2.PaymentData | None = None
        self.default_error: Exception | None = None

    def configure_token_response(
        self,
        payment_token: str,
        card_number: str,
        exp_month: int = 12,
        exp_year: int = 2025,
        cvv: str = "123",
        cardholder_name: str = "Test Cardholder",
        billing_zip: str | None = "12345",
    ) -> None:
        """
        Configure a successful response for a specific payment token.

        Args:
            payment_token: Payment token to configure
            card_number: Card number to return
            exp_month: Expiration month
            exp_year: Expiration year
            cvv: CVV code
            cardholder_name: Cardholder name
            billing_zip: Billing ZIP code (optional)
        """
        payment_data = payment_token_pb2.PaymentData(
            card_number=card_number,
            exp_month=exp_month,
            exp_year=exp_year,
            cvv=cvv,
            cardholder_name=cardholder_name,
        )

        if billing_zip:
            payment_data.billing_zip = billing_zip

        self.token_responses[payment_token] = payment_data

    def configure_token_error(self, payment_token: str, error: Exception) -> None:
        """
        Configure an error response for a specific payment token.

        Args:
            payment_token: Payment token to configure
            error: Exception to raise (TokenNotFound, TokenExpired, Forbidden, ProcessorTimeout)
        """
        self.token_responses[payment_token] = error

    def configure_default_response(
        self,
        card_number: str = "4242424242424242",
        exp_month: int = 12,
        exp_year: int = 2025,
        cvv: str = "123",
        cardholder_name: str = "Test Cardholder",
        billing_zip: str | None = "12345",
    ) -> None:
        """
        Configure the default response for any unmapped token.

        Args:
            card_number: Card number to return
            exp_month: Expiration month
            exp_year: Expiration year
            cvv: CVV code
            cardholder_name: Cardholder name
            billing_zip: Billing ZIP code (optional)
        """
        payment_data = payment_token_pb2.PaymentData(
            card_number=card_number,
            exp_month=exp_month,
            exp_year=exp_year,
            cvv=cvv,
            cardholder_name=cardholder_name,
        )

        if billing_zip:
            payment_data.billing_zip = billing_zip

        self.default_response = payment_data

    def configure_default_error(self, error: Exception) -> None:
        """
        Configure the default error for any unmapped token.

        Args:
            error: Exception to raise
        """
        self.default_error = error

    async def decrypt(
        self,
        payment_token: str,
        restaurant_id: str,
        requesting_service: str,
    ) -> payment_token_pb2.PaymentData:
        """
        Mock decrypt method that returns configured responses.

        Args:
            payment_token: Payment token to decrypt
            restaurant_id: Restaurant ID for authorization
            requesting_service: Requesting service name

        Returns:
            PaymentData protobuf with card information

        Raises:
            TokenNotFound, TokenExpired, Forbidden, ProcessorTimeout based on configuration
        """
        # Check for token-specific configuration
        if payment_token in self.token_responses:
            response = self.token_responses[payment_token]

            # If it's an exception, raise it
            if isinstance(response, Exception):
                raise response

            # Otherwise return the payment data
            return response

        # Use default response if configured
        if self.default_response:
            return self.default_response

        # Use default error if configured
        if self.default_error:
            raise self.default_error

        # Fall back to generic success response
        return payment_token_pb2.PaymentData(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test Cardholder",
            billing_zip="12345",
        )

    async def close(self) -> None:
        """Mock close method (no-op)."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


@pytest.fixture
def mock_payment_token_client(monkeypatch):
    """
    Fixture that patches PaymentTokenServiceClient with a mock implementation.

    This fixture:
    1. Creates a MockPaymentTokenServiceClient instance
    2. Patches the PaymentTokenServiceClient class to return the mock
    3. Yields the mock for test configuration
    4. Automatically reverts the patch after the test

    Usage:
        def test_something(mock_payment_token_client):
            # Configure the mock
            mock_payment_token_client.configure_token_response(
                payment_token="pt_test_12345",
                card_number="4242424242424242",
            )

            # Or configure an error
            mock_payment_token_client.configure_token_error(
                payment_token="pt_expired",
                error=TokenExpired("Token expired"),
            )

            # Run your test - the worker will use the mock
            ...

    Returns:
        MockPaymentTokenServiceClient: The mock client instance
    """
    from auth_processor_worker.clients import payment_token_client

    # Create mock instance
    mock_client = MockPaymentTokenServiceClient(
        base_url="http://mock:8000",
        service_auth_token="mock-token",
    )

    # Configure default success response
    mock_client.configure_default_response()

    # Patch the PaymentTokenServiceClient class
    # When code does: client = PaymentTokenServiceClient(...), it gets our mock
    def mock_client_factory(*args, **kwargs):
        return mock_client

    monkeypatch.setattr(
        payment_token_client,
        "PaymentTokenServiceClient",
        mock_client_factory,
    )

    yield mock_client


@pytest.fixture
def configure_token_success(mock_payment_token_client):
    """
    Helper fixture to quickly configure successful token responses.

    Usage:
        def test_something(configure_token_success):
            configure_token_success("pt_test_123", "4242424242424242")
            # Token will decrypt to Visa success card
    """
    def _configure(payment_token: str, card_number: str = "4242424242424242"):
        mock_payment_token_client.configure_token_response(
            payment_token=payment_token,
            card_number=card_number,
        )

    return _configure


@pytest.fixture
def configure_token_not_found(mock_payment_token_client):
    """
    Helper fixture to configure token not found (404) responses.

    Usage:
        def test_something(configure_token_not_found):
            configure_token_not_found("pt_missing_123")
    """
    def _configure(payment_token: str):
        mock_payment_token_client.configure_token_error(
            payment_token=payment_token,
            error=TokenNotFound(f"Token {payment_token} not found"),
        )

    return _configure


@pytest.fixture
def configure_token_expired(mock_payment_token_client):
    """
    Helper fixture to configure token expired (410) responses.

    Usage:
        def test_something(configure_token_expired):
            configure_token_expired("pt_old_123")
    """
    def _configure(payment_token: str):
        mock_payment_token_client.configure_token_error(
            payment_token=payment_token,
            error=TokenExpired(f"Token {payment_token} expired"),
        )

    return _configure


@pytest.fixture
def configure_token_forbidden(mock_payment_token_client):
    """
    Helper fixture to configure forbidden (403) responses.

    Usage:
        def test_something(configure_token_forbidden):
            configure_token_forbidden("pt_other_restaurant")
    """
    def _configure(payment_token: str):
        mock_payment_token_client.configure_token_error(
            payment_token=payment_token,
            error=Forbidden(f"Unauthorized access to token {payment_token}"),
        )

    return _configure


@pytest.fixture
def configure_token_timeout(mock_payment_token_client):
    """
    Helper fixture to configure timeout/5xx responses.

    Usage:
        def test_something(configure_token_timeout):
            configure_token_timeout("pt_slow_123")
    """
    def _configure(payment_token: str):
        mock_payment_token_client.configure_token_error(
            payment_token=payment_token,
            error=ProcessorTimeout("Payment Token Service timeout"),
        )

    return _configure
