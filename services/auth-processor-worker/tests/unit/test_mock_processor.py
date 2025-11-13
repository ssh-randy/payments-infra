"""Unit tests for MockProcessor."""

import pytest
from datetime import datetime

from auth_processor_worker.models import (
    AuthStatus,
    AuthorizationResult,
    PaymentData,
    ProcessorTimeout,
)
from auth_processor_worker.processors.mock_processor import MockProcessor


@pytest.fixture
def mock_processor():
    """Create a basic mock processor instance."""
    return MockProcessor()


@pytest.fixture
def sample_payment_data():
    """Create sample payment data for testing."""
    return PaymentData(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
        billing_zip="12345",
    )


@pytest.mark.asyncio
class TestMockProcessorSuccess:
    """Test successful authorization scenarios."""

    async def test_authorize_success_visa(self, mock_processor):
        """Test successful authorization with Visa test card."""
        payment_data = PaymentData(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
            billing_zip="12345",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.processor_name == "mock"
        assert result.processor_auth_id is not None
        assert result.processor_auth_id.startswith("mock_pi_")
        assert result.authorization_code is not None
        assert result.authorized_amount_cents == 1000
        assert result.currency == "USD"
        assert isinstance(result.authorized_at, datetime)
        assert result.processor_metadata is not None
        assert result.processor_metadata["status"] == "requires_capture"
        assert result.processor_metadata["card_brand"] == "visa"
        assert result.processor_metadata["card_last4"] == "4242"

    async def test_authorize_success_mastercard(self, mock_processor):
        """Test successful authorization with Mastercard test card."""
        payment_data = PaymentData(
            card_number="5555555555554444",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=5000,
            currency="EUR",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.authorized_amount_cents == 5000
        assert result.currency == "EUR"
        assert result.processor_metadata["card_brand"] == "mastercard"

    async def test_authorize_success_amex(self, mock_processor):
        """Test successful authorization with American Express test card."""
        payment_data = PaymentData(
            card_number="378282246310005",
            exp_month=12,
            exp_year=2025,
            cvv="1234",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=2500,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.processor_metadata["card_brand"] == "amex"
        assert result.processor_metadata["card_last4"] == "0005"

    async def test_authorize_with_metadata(self, mock_processor, sample_payment_data):
        """Test that config metadata is included in processor_metadata."""
        config = {
            "metadata": {
                "order_id": "order_123",
                "customer_id": "cust_456",
            }
        }

        result = await mock_processor.authorize(
            payment_data=sample_payment_data,
            amount_cents=1000,
            currency="USD",
            config=config,
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert "order_id" in result.processor_metadata
        assert result.processor_metadata["order_id"] == "order_123"
        assert "customer_id" in result.processor_metadata
        assert result.processor_metadata["customer_id"] == "cust_456"


@pytest.mark.asyncio
class TestMockProcessorDeclines:
    """Test card decline scenarios."""

    async def test_decline_generic(self, mock_processor):
        """Test generic card decline."""
        payment_data = PaymentData(
            card_number="4000000000000002",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.processor_name == "mock"
        assert result.denial_code == "card_declined"
        assert result.denial_reason == "Your card was declined"
        assert result.processor_metadata["decline_code"] == "generic_decline"
        assert result.processor_metadata["test_card"] == "4000000000000002"

    async def test_decline_insufficient_funds(self, mock_processor):
        """Test insufficient funds decline."""
        payment_data = PaymentData(
            card_number="4000000000009995",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "card_declined"
        assert result.denial_reason == "Your card has insufficient funds"
        assert result.processor_metadata["decline_code"] == "insufficient_funds"

    async def test_decline_expired_card(self, mock_processor):
        """Test expired card decline."""
        payment_data = PaymentData(
            card_number="4000000000000069",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "expired_card"
        assert result.denial_reason == "Your card has expired"
        assert result.processor_metadata["decline_code"] == "expired_card"

    async def test_decline_incorrect_cvc(self, mock_processor):
        """Test incorrect CVC decline."""
        payment_data = PaymentData(
            card_number="4000000000000127",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "incorrect_cvc"
        assert result.denial_reason == "Your card's security code is incorrect"

    async def test_decline_lost_card(self, mock_processor):
        """Test lost card decline."""
        payment_data = PaymentData(
            card_number="4000000000000341",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "card_declined"
        assert result.processor_metadata["decline_code"] == "lost_card"

    async def test_decline_fraudulent(self, mock_processor):
        """Test fraudulent card decline."""
        payment_data = PaymentData(
            card_number="4000000000000226",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.processor_metadata["decline_code"] == "fraudulent"


@pytest.mark.asyncio
class TestMockProcessorErrors:
    """Test error and timeout scenarios."""

    async def test_timeout_retryable(self, mock_processor):
        """Test timeout scenario (should raise ProcessorTimeout)."""
        payment_data = PaymentData(
            card_number="4000000000000119",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        with pytest.raises(ProcessorTimeout) as exc_info:
            await mock_processor.authorize(
                payment_data=payment_data,
                amount_cents=1000,
                currency="USD",
                config={},
            )

        assert "timeout" in str(exc_info.value).lower()

    async def test_rate_limit_retryable(self, mock_processor):
        """Test rate limit scenario (should raise ProcessorTimeout)."""
        payment_data = PaymentData(
            card_number="4000000000009987",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        with pytest.raises(ProcessorTimeout) as exc_info:
            await mock_processor.authorize(
                payment_data=payment_data,
                amount_cents=1000,
                currency="USD",
                config={},
            )

        assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestMockProcessorRequiresAction:
    """Test 3D Secure / requires_action scenarios."""

    async def test_requires_action(self, mock_processor):
        """Test 3D Secure authentication required scenario."""
        payment_data = PaymentData(
            card_number="4000002500003155",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "requires_action"
        assert result.denial_reason == "Payment requires additional authentication"
        assert result.processor_metadata["status"] == "requires_action"


@pytest.mark.asyncio
class TestMockProcessorConfiguration:
    """Test configuration options."""

    async def test_custom_latency(self):
        """Test custom latency configuration."""
        import time

        processor = MockProcessor(config={"latency_ms": 100})

        payment_data = PaymentData(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        start = time.time()
        result = await processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )
        elapsed = time.time() - start

        assert result.status == AuthStatus.AUTHORIZED
        assert elapsed >= 0.1  # Should take at least 100ms

    async def test_default_response_authorized(self):
        """Test default response for unknown cards (authorized)."""
        processor = MockProcessor(config={"default_response": "authorized"})

        payment_data = PaymentData(
            card_number="9999999999999999",  # Unknown card
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED

    async def test_default_response_declined(self):
        """Test default response for unknown cards (declined)."""
        processor = MockProcessor(config={"default_response": "declined"})

        payment_data = PaymentData(
            card_number="9999999999999999",  # Unknown card
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.DENIED

    async def test_custom_card_behaviors(self):
        """Test custom card behavior overrides."""
        custom_behaviors = {
            "1111111111111111": {
                "type": "success",
                "auth_code": "CUSTOM123",
                "description": "Custom success card",
            }
        }

        processor = MockProcessor(config={"card_behaviors": custom_behaviors})

        payment_data = PaymentData(
            card_number="1111111111111111",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.authorization_code == "CUSTOM123"


@pytest.mark.asyncio
class TestMockProcessorCardBrandDetection:
    """Test card brand detection logic."""

    async def test_visa_detection(self, mock_processor):
        """Test Visa card brand detection."""
        payment_data = PaymentData(
            card_number="4111111111111111",  # Visa
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.processor_metadata["card_brand"] == "visa"

    async def test_mastercard_detection(self, mock_processor):
        """Test Mastercard brand detection."""
        payment_data = PaymentData(
            card_number="5105105105105100",  # Mastercard
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.processor_metadata["card_brand"] == "mastercard"

    async def test_amex_detection(self, mock_processor):
        """Test American Express brand detection."""
        payment_data = PaymentData(
            card_number="371449635398431",  # Amex
            exp_month=12,
            exp_year=2025,
            cvv="1234",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.processor_metadata["card_brand"] == "amex"

    async def test_discover_detection(self, mock_processor):
        """Test Discover card brand detection."""
        payment_data = PaymentData(
            card_number="6011111111111117",  # Discover
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.processor_metadata["card_brand"] == "discover"


@pytest.mark.asyncio
class TestMockProcessorMetadataStructure:
    """Test that metadata structure matches Stripe's format."""

    async def test_success_metadata_structure(self, mock_processor, sample_payment_data):
        """Test that success response metadata matches Stripe's structure."""
        result = await mock_processor.authorize(
            payment_data=sample_payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        # These fields should match Stripe's PaymentIntent structure
        assert "payment_intent_id" in result.processor_metadata
        assert "status" in result.processor_metadata
        assert "client_secret" in result.processor_metadata
        assert "charge_id" in result.processor_metadata
        assert "payment_method_id" in result.processor_metadata
        assert "card_brand" in result.processor_metadata
        assert "card_last4" in result.processor_metadata

        # Verify format of IDs matches Stripe's pattern
        assert result.processor_metadata["payment_intent_id"].startswith("mock_pi_")
        assert result.processor_metadata["charge_id"].startswith("mock_ch_")
        assert result.processor_metadata["payment_method_id"].startswith("mock_pm_")
        assert result.processor_metadata["status"] == "requires_capture"

    async def test_decline_metadata_structure(self, mock_processor):
        """Test that decline response metadata matches Stripe's structure."""
        payment_data = PaymentData(
            card_number="4000000000000002",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test User",
        )

        result = await mock_processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        # These fields should match Stripe's CardError structure
        assert "decline_code" in result.processor_metadata
        assert "charge_id" in result.processor_metadata or result.processor_metadata.get("charge_id") is not None
        assert "payment_intent_id" in result.processor_metadata
        assert "test_card" in result.processor_metadata
