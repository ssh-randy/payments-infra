"""
Integration tests that call the REAL Stripe API.

These tests use the Stripe test API key from .env and make actual HTTP calls
to Stripe's servers. They verify that our Stripe processor integration works
correctly with Stripe's actual API.

Requirements:
- STRIPE__API_KEY must be set in .env (use a test key: sk_test_...)
- Internet connection required
- Tests use Stripe's test card numbers
"""

import sys
from pathlib import Path

import pytest
import stripe

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from auth_processor_worker.config import settings
from auth_processor_worker.models.authorization import AuthStatus, PaymentData
from auth_processor_worker.processors.stripe_processor import StripeProcessor


@pytest.fixture
def stripe_processor():
    """Create a real Stripe processor with API key from .env."""
    if not settings.stripe.api_key or settings.stripe.api_key == "":
        pytest.skip("STRIPE__API_KEY not configured in .env")

    return StripeProcessor(
        api_key=settings.stripe.api_key,
        timeout_seconds=settings.stripe.timeout_seconds,
    )


@pytest.fixture
def successful_payment_data():
    """Payment data using Stripe's test card that succeeds."""
    return PaymentData(
        card_number="4242424242424242",  # Stripe test card - always succeeds
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="Test Customer",
        billing_zip="12345",
    )


@pytest.fixture
def declined_payment_data():
    """Payment data using Stripe's test card that gets declined."""
    return PaymentData(
        card_number="4000000000000002",  # Stripe test card - always declines
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="Test Customer",
        billing_zip="12345",
    )


@pytest.fixture
def insufficient_funds_payment_data():
    """Payment data using Stripe's test card for insufficient funds."""
    return PaymentData(
        card_number="4000000000009995",  # Stripe test card - insufficient funds
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="Test Customer",
        billing_zip="12345",
    )


@pytest.mark.integration
class TestStripeRealAPIAuthorization:
    """Test successful authorization against real Stripe API."""

    @pytest.mark.asyncio
    async def test_successful_authorization_real_api(
        self, stripe_processor, successful_payment_data
    ):
        """Test successful authorization with Stripe's test API."""
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1050,  # $10.50
            currency="USD",
            config={
                "statement_descriptor": "TEST CHARGE",
                "metadata": {"test": "true", "source": "integration_test"},
            },
        )

        # Verify authorization succeeded
        assert result.status == AuthStatus.AUTHORIZED
        assert result.processor_name == "stripe"
        assert result.processor_auth_id.startswith("pi_")  # PaymentIntent ID
        assert result.authorized_amount_cents == 1050
        assert result.currency == "USD"
        # Note: authorization_code may be None if charges aren't expanded in API response
        assert result.authorized_at is not None

        # Verify metadata
        assert "payment_intent_id" in result.processor_metadata
        assert result.processor_metadata["payment_intent_id"] == result.processor_auth_id

        print(f"\n✅ Authorization successful: {result.processor_auth_id}")
        print(f"   Authorization code: {result.authorization_code}")
        print(f"   Amount: ${result.authorized_amount_cents / 100:.2f}")

    @pytest.mark.asyncio
    async def test_authorization_is_uncaptured(
        self, stripe_processor, successful_payment_data
    ):
        """
        Test that authorization does NOT capture funds (auth-only).

        This verifies the critical requirement: we authorize but don't capture
        until the order is fulfilled.
        """
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=2000,  # $20.00
            currency="USD",
            config={"metadata": {"test": "auth_only"}},
        )

        assert result.status == AuthStatus.AUTHORIZED

        # Retrieve the PaymentIntent from Stripe to verify it's uncaptured
        stripe.api_key = settings.stripe.api_key
        payment_intent = stripe.PaymentIntent.retrieve(result.processor_auth_id)

        # Critical assertion: status should be requires_capture, not succeeded
        assert payment_intent.status == "requires_capture"
        assert payment_intent.amount == 2000
        assert payment_intent.capture_method == "manual"

        print(f"\n✅ Authorization created without capture: {payment_intent.id}")
        print(f"   Status: {payment_intent.status} (requires_capture)")
        print(f"   Amount: ${payment_intent.amount / 100:.2f}")

    @pytest.mark.asyncio
    async def test_authorization_can_be_captured_later(
        self, stripe_processor, successful_payment_data
    ):
        """
        Test that an authorization can be captured later.

        This simulates the full workflow:
        1. Authorize when order is placed
        2. Capture when order is fulfilled
        """
        # Step 1: Authorize
        auth_result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1500,  # $15.00
            currency="USD",
            config={"metadata": {"test": "capture_later"}},
        )

        assert auth_result.status == AuthStatus.AUTHORIZED
        payment_intent_id = auth_result.processor_auth_id

        # Step 2: Capture (simulating later fulfillment)
        stripe.api_key = settings.stripe.api_key
        payment_intent = stripe.PaymentIntent.capture(payment_intent_id)

        # Verify capture succeeded
        assert payment_intent.status == "succeeded"
        assert payment_intent.amount == 1500
        assert payment_intent.amount_received == 1500

        print(f"\n✅ Authorization captured successfully")
        print(f"   PaymentIntent: {payment_intent_id}")
        print(f"   Status after capture: {payment_intent.status}")
        print(f"   Amount captured: ${payment_intent.amount_received / 100:.2f}")

    @pytest.mark.asyncio
    async def test_authorization_can_be_canceled(
        self, stripe_processor, successful_payment_data
    ):
        """
        Test that an authorization can be canceled (voided).

        This simulates order cancellation before fulfillment.
        """
        # Authorize
        auth_result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1200,  # $12.00
            currency="USD",
            config={"metadata": {"test": "void_test"}},
        )

        assert auth_result.status == AuthStatus.AUTHORIZED
        payment_intent_id = auth_result.processor_auth_id

        # Cancel the authorization
        stripe.api_key = settings.stripe.api_key
        payment_intent = stripe.PaymentIntent.cancel(payment_intent_id)

        # Verify cancellation
        assert payment_intent.status == "canceled"

        print(f"\n✅ Authorization canceled successfully")
        print(f"   PaymentIntent: {payment_intent_id}")
        print(f"   Status: {payment_intent.status}")

    @pytest.mark.asyncio
    async def test_authorization_with_different_amounts(
        self, stripe_processor, successful_payment_data
    ):
        """Test authorizations with various amounts."""
        test_amounts = [
            (100, "$1.00"),      # Small amount
            (2500, "$25.00"),    # Medium amount
            (50000, "$500.00"),  # Larger amount
        ]

        for amount_cents, display in test_amounts:
            result = await stripe_processor.authorize(
                payment_data=successful_payment_data,
                amount_cents=amount_cents,
                currency="USD",
                config={"metadata": {"amount_test": display}},
            )

            assert result.status == AuthStatus.AUTHORIZED
            assert result.authorized_amount_cents == amount_cents

            print(f"\n✅ Authorized {display}: {result.processor_auth_id}")


@pytest.mark.integration
class TestStripeRealAPIDeclines:
    """Test card declines against real Stripe API."""

    @pytest.mark.asyncio
    async def test_generic_card_decline(
        self, stripe_processor, declined_payment_data
    ):
        """Test generic card decline with Stripe's test card."""
        result = await stripe_processor.authorize(
            payment_data=declined_payment_data,
            amount_cents=1000,
            currency="USD",
            config={"metadata": {"test": "generic_decline"}},
        )

        # Should return DENIED, not throw exception
        assert result.status == AuthStatus.DENIED
        assert result.processor_name == "stripe"
        assert result.denial_code is not None
        assert result.denial_reason is not None

        print(f"\n❌ Card declined (expected)")
        print(f"   Denial code: {result.denial_code}")
        print(f"   Reason: {result.denial_reason}")

    @pytest.mark.asyncio
    async def test_insufficient_funds_decline(
        self, stripe_processor, insufficient_funds_payment_data
    ):
        """Test insufficient funds decline with Stripe's test card."""
        result = await stripe_processor.authorize(
            payment_data=insufficient_funds_payment_data,
            amount_cents=1000,
            currency="USD",
            config={"metadata": {"test": "insufficient_funds"}},
        )

        assert result.status == AuthStatus.DENIED
        assert "insufficient" in result.denial_reason.lower() or "funds" in result.denial_reason.lower()

        print(f"\n❌ Insufficient funds (expected)")
        print(f"   Denial code: {result.denial_code}")
        print(f"   Reason: {result.denial_reason}")


@pytest.mark.integration
class TestStripeRealAPIConfiguration:
    """Test configuration options against real Stripe API."""

    @pytest.mark.asyncio
    async def test_statement_descriptor(
        self, stripe_processor, successful_payment_data
    ):
        """Test that statement descriptor is properly set."""
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1000,
            currency="USD",
            config={"statement_descriptor": "CUSTOM DESC"},
        )

        assert result.status == AuthStatus.AUTHORIZED

        # Verify with Stripe API
        stripe.api_key = settings.stripe.api_key
        payment_intent = stripe.PaymentIntent.retrieve(result.processor_auth_id)

        # Statement descriptor suffix should be set (Stripe uses suffix for card payments)
        # Note: Stripe may modify/truncate it
        assert payment_intent.statement_descriptor_suffix is not None
        assert "CUSTOM DESC" in payment_intent.statement_descriptor_suffix

        print(f"\n✅ Statement descriptor set")
        print(f"   Requested: CUSTOM DESC")
        print(f"   Actual suffix: {payment_intent.statement_descriptor_suffix}")

    @pytest.mark.asyncio
    async def test_metadata_preservation(
        self, stripe_processor, successful_payment_data
    ):
        """Test that metadata is preserved in Stripe."""
        custom_metadata = {
            "order_id": "order_12345",
            "customer_id": "cust_67890",
            "restaurant_id": "rest_abc",
        }

        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1000,
            currency="USD",
            config={"metadata": custom_metadata},
        )

        assert result.status == AuthStatus.AUTHORIZED

        # Verify metadata with Stripe API
        stripe.api_key = settings.stripe.api_key
        payment_intent = stripe.PaymentIntent.retrieve(result.processor_auth_id)

        assert payment_intent.metadata["order_id"] == "order_12345"
        assert payment_intent.metadata["customer_id"] == "cust_67890"
        assert payment_intent.metadata["restaurant_id"] == "rest_abc"

        print(f"\n✅ Metadata preserved correctly")
        for key, value in payment_intent.metadata.items():
            print(f"   {key}: {value}")


@pytest.mark.integration
class TestStripeRealAPICurrencies:
    """Test different currencies against real Stripe API."""

    @pytest.mark.asyncio
    async def test_usd_authorization(
        self, stripe_processor, successful_payment_data
    ):
        """Test USD authorization."""
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.currency == "USD"

    @pytest.mark.asyncio
    async def test_eur_authorization(
        self, stripe_processor, successful_payment_data
    ):
        """Test EUR authorization."""
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1000,
            currency="EUR",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.currency == "EUR"

    @pytest.mark.asyncio
    async def test_gbp_authorization(
        self, stripe_processor, successful_payment_data
    ):
        """Test GBP authorization."""
        result = await stripe_processor.authorize(
            payment_data=successful_payment_data,
            amount_cents=1000,
            currency="GBP",
            config={},
        )

        assert result.status == AuthStatus.AUTHORIZED
        assert result.currency == "GBP"


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
