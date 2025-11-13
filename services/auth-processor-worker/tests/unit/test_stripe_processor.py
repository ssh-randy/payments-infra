"""Unit tests for Stripe processor integration."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import stripe
from stripe.error import APIError, CardError, RateLimitError

from auth_processor_worker.models import (
    AuthStatus,
    AuthorizationResult,
    PaymentData,
    ProcessorTimeout,
)
from auth_processor_worker.processors.stripe_processor import StripeProcessor


@pytest.fixture
def stripe_processor() -> StripeProcessor:
    """Create a StripeProcessor instance for testing."""
    return StripeProcessor(api_key="sk_test_fake_key", timeout_seconds=10)


@pytest.fixture
def sample_payment_data() -> PaymentData:
    """Create sample payment data for testing."""
    return PaymentData(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test Customer",
        billing_zip="12345",
    )


@pytest.fixture
def sample_config() -> dict:
    """Create sample processor config for testing."""
    return {
        "statement_descriptor": "Test Charge",
        "metadata": {"order_id": "12345"},
        "return_url": "https://example.com/return",
    }


class TestStripeProcessorSuccess:
    """Tests for successful authorization scenarios."""

    @pytest.mark.asyncio
    async def test_successful_authorization(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test successful card authorization."""
        # Mock successful payment intent creation
        mock_charge = MagicMock()
        mock_charge.id = "ch_test123"
        mock_charge.authorization_code = "123456"

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_capture"
        mock_intent.amount = 1000
        mock_intent.currency = "usd"
        mock_intent.created = 1234567890
        mock_intent.client_secret = "pi_test123_secret"
        mock_intent.payment_method = "pm_test123"
        mock_intent.charges.data = [mock_charge]

        with patch.object(stripe.PaymentIntent, "create", return_value=mock_intent):
            result = await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=sample_config,
            )

        # Assertions
        assert result.status == AuthStatus.AUTHORIZED
        assert result.processor_name == "stripe"
        assert result.processor_auth_id == "pi_test123"
        assert result.authorization_code == "123456"
        assert result.authorized_amount_cents == 1000
        assert result.currency == "USD"
        assert isinstance(result.authorized_at, datetime)
        assert result.processor_metadata is not None
        assert result.processor_metadata["payment_intent_id"] == "pi_test123"
        assert result.processor_metadata["charge_id"] == "ch_test123"

    @pytest.mark.asyncio
    async def test_authorization_without_zip(
        self,
        stripe_processor: StripeProcessor,
        sample_config: dict,
    ) -> None:
        """Test authorization with payment data that has no billing zip."""
        payment_data = PaymentData(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            cardholder_name="Test Customer",
            billing_zip=None,
        )

        mock_charge = MagicMock()
        mock_charge.id = "ch_test123"
        mock_charge.authorization_code = "123456"

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_capture"
        mock_intent.amount = 1000
        mock_intent.currency = "usd"
        mock_intent.created = 1234567890
        mock_intent.client_secret = "pi_test123_secret"
        mock_intent.payment_method = "pm_test123"
        mock_intent.charges.data = [mock_charge]

        with patch.object(stripe.PaymentIntent, "create", return_value=mock_intent):
            result = await stripe_processor.authorize(
                payment_data=payment_data,
                amount_cents=1000,
                currency="USD",
                config=sample_config,
            )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.processor_auth_id == "pi_test123"


class TestStripeProcessorDeclines:
    """Tests for card decline scenarios."""

    @pytest.mark.asyncio
    async def test_card_declined_insufficient_funds(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test card declined due to insufficient funds."""
        # Create a mock CardError with proper JSON body structure
        error_json = {
            "error": {
                "message": "Your card has insufficient funds.",
                "code": "card_declined",
                "decline_code": "insufficient_funds",
                "charge": "ch_test_declined",
                "param": "card",
            }
        }
        card_error = CardError(
            message="Your card has insufficient funds.",
            param="card",
            code="card_declined",
            http_status=402,
            json_body=error_json,
        )

        with patch.object(stripe.PaymentIntent, "create", side_effect=card_error):
            result = await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=sample_config,
            )

        # Assertions
        assert result.status == AuthStatus.DENIED
        assert result.processor_name == "stripe"
        assert result.denial_code == "card_declined"
        assert "insufficient funds" in result.denial_reason.lower()
        assert result.processor_metadata is not None
        assert result.processor_metadata["decline_code"] == "insufficient_funds"

    @pytest.mark.asyncio
    async def test_card_declined_expired(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test card declined due to expired card."""
        error_json = {
            "error": {
                "message": "Your card has expired.",
                "code": "expired_card",
                "decline_code": "expired_card",
                "param": "exp_year",
            }
        }
        card_error = CardError(
            message="Your card has expired.",
            param="exp_year",
            code="expired_card",
            http_status=402,
            json_body=error_json,
        )

        with patch.object(stripe.PaymentIntent, "create", side_effect=card_error):
            result = await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=sample_config,
            )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "expired_card"
        assert "expired" in result.denial_reason.lower()

    @pytest.mark.asyncio
    async def test_requires_action(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test payment requiring additional action (3DS)."""
        mock_next_action = MagicMock()
        mock_next_action.type = "redirect_to_url"

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_action"
        mock_intent.next_action = mock_next_action

        with patch.object(stripe.PaymentIntent, "create", return_value=mock_intent):
            result = await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=sample_config,
            )

        assert result.status == AuthStatus.DENIED
        assert result.denial_code == "requires_action"
        assert "authentication" in result.denial_reason.lower()


class TestStripeProcessorErrors:
    """Tests for error handling and retryable failures."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test that rate limit errors raise ProcessorTimeout."""
        rate_limit_error = RateLimitError(
            message="Too many requests",
            http_status=429,
        )

        with patch.object(stripe.PaymentIntent, "create", side_effect=rate_limit_error):
            with pytest.raises(ProcessorTimeout) as exc_info:
                await stripe_processor.authorize(
                    payment_data=sample_payment_data,
                    amount_cents=1000,
                    currency="USD",
                    config=sample_config,
                )

            assert "rate limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_api_error(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test that API errors raise ProcessorTimeout."""
        api_error = APIError(
            message="Internal server error",
            http_status=500,
        )

        with patch.object(stripe.PaymentIntent, "create", side_effect=api_error):
            with pytest.raises(ProcessorTimeout) as exc_info:
                await stripe_processor.authorize(
                    payment_data=sample_payment_data,
                    amount_cents=1000,
                    currency="USD",
                    config=sample_config,
                )

            assert "API error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unexpected_error(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
        sample_config: dict,
    ) -> None:
        """Test that unexpected errors raise ProcessorTimeout."""
        with patch.object(
            stripe.PaymentIntent,
            "create",
            side_effect=Exception("Unexpected error"),
        ):
            with pytest.raises(ProcessorTimeout) as exc_info:
                await stripe_processor.authorize(
                    payment_data=sample_payment_data,
                    amount_cents=1000,
                    currency="USD",
                    config=sample_config,
                )

            assert "Unexpected" in str(exc_info.value)


class TestStripeProcessorConfiguration:
    """Tests for processor configuration handling."""

    @pytest.mark.asyncio
    async def test_uses_config_statement_descriptor(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
    ) -> None:
        """Test that statement descriptor from config is used."""
        config = {"statement_descriptor": "CUSTOM DESC"}

        mock_charge = MagicMock()
        mock_charge.id = "ch_test123"
        mock_charge.authorization_code = "123456"

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_capture"
        mock_intent.amount = 1000
        mock_intent.currency = "usd"
        mock_intent.created = 1234567890
        mock_intent.client_secret = "pi_test123_secret"
        mock_intent.payment_method = "pm_test123"
        mock_intent.charges.data = [mock_charge]

        with patch.object(
            stripe.PaymentIntent, "create", return_value=mock_intent
        ) as mock_create:
            await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=config,
            )

            # Verify the statement descriptor was passed
            # Note: Stripe uses statement_descriptor_suffix for card payments
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["statement_descriptor_suffix"] == "CUSTOM DESC"

    @pytest.mark.asyncio
    async def test_uses_config_metadata(
        self,
        stripe_processor: StripeProcessor,
        sample_payment_data: PaymentData,
    ) -> None:
        """Test that metadata from config is used."""
        config = {"metadata": {"order_id": "12345", "customer_id": "cust_123"}}

        mock_charge = MagicMock()
        mock_charge.id = "ch_test123"
        mock_charge.authorization_code = "123456"

        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.status = "requires_capture"
        mock_intent.amount = 1000
        mock_intent.currency = "usd"
        mock_intent.created = 1234567890
        mock_intent.client_secret = "pi_test123_secret"
        mock_intent.payment_method = "pm_test123"
        mock_intent.charges.data = [mock_charge]

        with patch.object(
            stripe.PaymentIntent, "create", return_value=mock_intent
        ) as mock_create:
            await stripe_processor.authorize(
                payment_data=sample_payment_data,
                amount_cents=1000,
                currency="USD",
                config=config,
            )

            # Verify metadata was passed
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["metadata"]["order_id"] == "12345"
            assert call_kwargs["metadata"]["customer_id"] == "cust_123"
