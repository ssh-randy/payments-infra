"""
Integration tests using Stripe test tokens instead of raw card data.

This approach:
1. Works immediately (no Stripe approval needed)
2. Tests the actual Stripe API integration
3. Validates auth/capture/void flows
4. Doesn't test the Payment Token Service integration (use separate tests for that)

Test tokens: https://docs.stripe.com/testing#cards
"""

import pytest
import stripe

from auth_processor_worker.config import settings


@pytest.fixture
def stripe_api_key():
    """Get Stripe API key from settings."""
    if not settings.stripe.api_key or settings.stripe.api_key == "":
        pytest.skip("STRIPE__API_KEY not configured in .env")
    return settings.stripe.api_key


@pytest.mark.integration
class TestStripeWithTokens:
    """Test Stripe integration using test tokens (no raw card data)."""

    def test_authorization_with_token(self, stripe_api_key):
        """Test successful authorization using Stripe test token."""
        stripe.api_key = stripe_api_key

        # Create PaymentIntent with test token
        payment_intent = stripe.PaymentIntent.create(
            amount=1050,  # $10.50
            currency="usd",
            capture_method="manual",  # Authorization only
            payment_method="pm_card_visa",  # Test token for Visa
            confirm=True,
            return_url="https://example.com/return",
            statement_descriptor_suffix="TEST CHARGE",
            metadata={"test": "true", "source": "integration_test"},
        )

        # Verify authorization succeeded
        assert payment_intent.status == "requires_capture"
        assert payment_intent.amount == 1050
        assert payment_intent.currency == "usd"
        assert payment_intent.capture_method == "manual"

        print(f"\n✅ Authorization successful: {payment_intent.id}")
        print(f"   Status: {payment_intent.status}")
        print(f"   Amount: ${payment_intent.amount / 100:.2f}")

    def test_authorization_then_capture(self, stripe_api_key):
        """Test full auth + capture flow."""
        stripe.api_key = stripe_api_key

        # Step 1: Authorize
        payment_intent = stripe.PaymentIntent.create(
            amount=1500,
            currency="usd",
            capture_method="manual",
            payment_method="pm_card_mastercard",  # Test Mastercard
            confirm=True,
            return_url="https://example.com/return",
        )

        assert payment_intent.status == "requires_capture"
        print(f"\n✅ Authorization created: {payment_intent.id}")

        # Step 2: Capture
        captured = stripe.PaymentIntent.capture(payment_intent.id)

        assert captured.status == "succeeded"
        assert captured.amount_received == 1500
        print(f"✅ Captured successfully: ${captured.amount_received / 100:.2f}")

    def test_authorization_then_cancel(self, stripe_api_key):
        """Test auth + void (cancel) flow."""
        stripe.api_key = stripe_api_key

        # Authorize
        payment_intent = stripe.PaymentIntent.create(
            amount=1200,
            currency="usd",
            capture_method="manual",
            payment_method="pm_card_visa",
            confirm=True,
            return_url="https://example.com/return",
        )

        assert payment_intent.status == "requires_capture"
        print(f"\n✅ Authorization created: {payment_intent.id}")

        # Cancel (void)
        canceled = stripe.PaymentIntent.cancel(payment_intent.id)

        assert canceled.status == "canceled"
        print(f"✅ Voided successfully: {canceled.id}")

    def test_declined_card(self, stripe_api_key):
        """Test card decline using Stripe's decline test token."""
        stripe.api_key = stripe_api_key

        try:
            # This token always declines
            payment_intent = stripe.PaymentIntent.create(
                amount=1000,
                currency="usd",
                capture_method="manual",
                payment_method="pm_card_chargeDeclined",  # Always declines
                confirm=True,
                return_url="https://example.com/return",
            )

            # Should not get here
            assert False, "Expected decline but got success"

        except stripe.error.CardError as e:
            # Expected decline
            print(f"\n❌ Card declined (expected): {e.user_message}")
            assert e.code == "card_declined"

    def test_insufficient_funds(self, stripe_api_key):
        """Test insufficient funds decline."""
        stripe.api_key = stripe_api_key

        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=1000,
                currency="usd",
                capture_method="manual",
                payment_method="pm_card_chargeDeclinedInsufficientFunds",
                confirm=True,
                return_url="https://example.com/return",
            )

            assert False, "Expected insufficient funds decline"

        except stripe.error.CardError as e:
            print(f"\n❌ Insufficient funds (expected): {e.user_message}")
            assert "insufficient" in e.user_message.lower() or "funds" in e.user_message.lower()

    def test_metadata_preservation(self, stripe_api_key):
        """Test that metadata is preserved."""
        stripe.api_key = stripe_api_key

        custom_metadata = {
            "order_id": "order_12345",
            "customer_id": "cust_67890",
            "restaurant_id": "rest_abc",
        }

        payment_intent = stripe.PaymentIntent.create(
            amount=1000,
            currency="usd",
            capture_method="manual",
            payment_method="pm_card_visa",
            confirm=True,
            return_url="https://example.com/return",
            metadata=custom_metadata,
        )

        # Verify metadata
        assert payment_intent.metadata["order_id"] == "order_12345"
        assert payment_intent.metadata["customer_id"] == "cust_67890"
        assert payment_intent.metadata["restaurant_id"] == "rest_abc"

        print(f"\n✅ Metadata preserved:")
        for key, value in payment_intent.metadata.items():
            print(f"   {key}: {value}")

    def test_different_currencies(self, stripe_api_key):
        """Test different currencies."""
        stripe.api_key = stripe_api_key

        currencies = ["usd", "eur", "gbp"]

        for currency in currencies:
            payment_intent = stripe.PaymentIntent.create(
                amount=1000,
                currency=currency,
                capture_method="manual",
                payment_method="pm_card_visa",
                confirm=True,
                return_url="https://example.com/return",
            )

            assert payment_intent.status == "requires_capture"
            assert payment_intent.currency == currency

            print(f"\n✅ {currency.upper()} authorization: {payment_intent.id}")

    def test_various_amounts(self, stripe_api_key):
        """Test different authorization amounts."""
        stripe.api_key = stripe_api_key

        amounts = [
            (100, "$1.00"),
            (2500, "$25.00"),
            (50000, "$500.00"),
        ]

        for amount_cents, display in amounts:
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                capture_method="manual",
                payment_method="pm_card_visa",
                confirm=True,
                return_url="https://example.com/return",
            )

            assert payment_intent.status == "requires_capture"
            assert payment_intent.amount == amount_cents

            print(f"\n✅ Authorized {display}: {payment_intent.id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
