"""
Example usage of MockProcessor for testing.

This example demonstrates how to use the MockProcessor in tests and
development environments to simulate payment authorization without
making real API calls.
"""

import asyncio
from auth_processor_worker.models import AuthStatus, PaymentData
from auth_processor_worker.processors import MockProcessor


async def example_basic_usage():
    """Basic mock processor usage - success scenario."""
    print("=== Example 1: Basic Usage (Success) ===\n")

    # Create mock processor with default settings
    processor = MockProcessor()

    # Create payment data with a success test card
    payment_data = PaymentData(
        card_number="4242424242424242",  # Visa success card
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
        billing_zip="12345",
    )

    # Authorize payment
    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=1000,  # $10.00
        currency="USD",
        config={},
    )

    print(f"Status: {result.status}")
    print(f"Processor: {result.processor_name}")
    print(f"Auth ID: {result.processor_auth_id}")
    print(f"Auth Code: {result.authorization_code}")
    print(f"Amount: ${result.authorized_amount_cents / 100:.2f}")
    print(f"Currency: {result.currency}")
    print(f"Metadata: {result.processor_metadata}")
    print()


async def example_decline_scenario():
    """Test card decline scenario."""
    print("=== Example 2: Card Decline (Insufficient Funds) ===\n")

    processor = MockProcessor()

    # Use a test card that simulates insufficient funds
    payment_data = PaymentData(
        card_number="4000000000009995",  # Insufficient funds
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
    )

    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=5000,  # $50.00
        currency="USD",
        config={},
    )

    print(f"Status: {result.status}")
    print(f"Denial Code: {result.denial_code}")
    print(f"Denial Reason: {result.denial_reason}")
    print(f"Decline Code: {result.processor_metadata.get('decline_code')}")
    print()


async def example_timeout_scenario():
    """Test timeout scenario (retryable error)."""
    print("=== Example 3: Timeout (Retryable Error) ===\n")

    processor = MockProcessor()

    # Use a test card that simulates timeout
    payment_data = PaymentData(
        card_number="4000000000000119",  # Timeout card
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
    )

    try:
        result = await processor.authorize(
            payment_data=payment_data,
            amount_cents=1000,
            currency="USD",
            config={},
        )
    except Exception as e:
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception Message: {e}")
        print("(This error should be retried)")
    print()


async def example_custom_configuration():
    """Custom configuration - latency and default behavior."""
    print("=== Example 4: Custom Configuration ===\n")

    # Configure with custom latency and default response
    processor = MockProcessor(
        config={
            "default_response": "authorized",
            "latency_ms": 100,  # Simulate 100ms network latency
        }
    )

    # Use an unknown card number
    payment_data = PaymentData(
        card_number="9999999999999999",  # Unknown card
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
    )

    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=2500,
        currency="USD",
        config={},
    )

    print(f"Unknown card behavior: {result.status}")
    print("(Used default_response='authorized')")
    print()


async def example_with_metadata():
    """Include metadata in authorization request."""
    print("=== Example 5: Authorization with Metadata ===\n")

    processor = MockProcessor()

    payment_data = PaymentData(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
    )

    # Include custom metadata
    config = {
        "metadata": {
            "order_id": "order_123456",
            "customer_id": "cust_789",
            "source": "mobile_app",
        }
    }

    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=7500,  # $75.00
        currency="USD",
        config=config,
    )

    print(f"Status: {result.status}")
    print("Metadata in result:")
    print(f"  - order_id: {result.processor_metadata.get('order_id')}")
    print(f"  - customer_id: {result.processor_metadata.get('customer_id')}")
    print(f"  - source: {result.processor_metadata.get('source')}")
    print()


async def example_all_test_cards():
    """Demonstrate all available test card scenarios."""
    print("=== Example 6: All Test Card Scenarios ===\n")

    processor = MockProcessor()

    test_scenarios = [
        ("4242424242424242", "Success - Visa"),
        ("5555555555554444", "Success - Mastercard"),
        ("378282246310005", "Success - Amex"),
        ("4000000000000002", "Decline - Generic"),
        ("4000000000009995", "Decline - Insufficient Funds"),
        ("4000000000000069", "Decline - Expired Card"),
        ("4000000000000127", "Decline - Incorrect CVC"),
        ("4000000000000341", "Decline - Lost Card"),
        ("4000000000000226", "Decline - Fraudulent"),
        ("4000002500003155", "Requires Action - 3D Secure"),
        ("4000000000000119", "Timeout - Retryable Error"),
        ("4000000000009987", "Rate Limit - Retryable Error"),
    ]

    for card_number, description in test_scenarios:
        payment_data = PaymentData(
            card_number=card_number,
            exp_month=12,
            exp_year=2025,
            cvv="123" if not card_number.startswith("37") else "1234",
            cardholder_name="Test User",
        )

        try:
            result = await processor.authorize(
                payment_data=payment_data,
                amount_cents=1000,
                currency="USD",
                config={},
            )

            print(f"✓ {description}")
            print(f"  Card: {card_number}")
            print(f"  Status: {result.status}")
            if result.status == AuthStatus.DENIED:
                print(f"  Reason: {result.denial_reason}")
            print()

        except Exception as e:
            print(f"✗ {description}")
            print(f"  Card: {card_number}")
            print(f"  Exception: {type(e).__name__}")
            print(f"  Message: {e}")
            print()


async def example_custom_card_behaviors():
    """Custom card behaviors for specific test scenarios."""
    print("=== Example 7: Custom Card Behaviors ===\n")

    # Define custom test cards for your specific use case
    custom_behaviors = {
        "1111111111111111": {
            "type": "success",
            "auth_code": "CUSTOM001",
            "description": "VIP customer card - always succeeds",
        },
        "2222222222222222": {
            "type": "decline",
            "code": "card_declined",
            "decline_code": "do_not_honor",
            "reason": "Card issuer declined the transaction",
            "description": "Test 'do not honor' decline",
        },
        "3333333333333333": {
            "type": "timeout",
            "description": "Simulates slow payment gateway",
        },
    }

    processor = MockProcessor(config={"card_behaviors": custom_behaviors})

    # Test custom VIP card
    payment_data = PaymentData(
        card_number="1111111111111111",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="VIP Customer",
    )

    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=10000,  # $100.00
        currency="USD",
        config={},
    )

    print(f"Custom VIP Card:")
    print(f"  Status: {result.status}")
    print(f"  Auth Code: {result.authorization_code}")
    print()


async def main():
    """Run all examples."""
    print("=" * 60)
    print("MockProcessor Usage Examples")
    print("=" * 60)
    print()

    await example_basic_usage()
    await example_decline_scenario()
    await example_timeout_scenario()
    await example_custom_configuration()
    await example_with_metadata()
    await example_all_test_cards()
    await example_custom_card_behaviors()

    print("=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
