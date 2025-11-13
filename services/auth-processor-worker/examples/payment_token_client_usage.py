"""Example usage of PaymentTokenServiceClient.

This example demonstrates how to use the Payment Token Service client
to decrypt payment tokens in the auth processor worker.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from auth_processor_worker.clients.payment_token_client import PaymentTokenServiceClient
from auth_processor_worker.config import settings
from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)


async def example_successful_decrypt():
    """Example: Successfully decrypt a payment token."""
    print("\n=== Example 1: Successful Decryption ===\n")

    async with PaymentTokenServiceClient(
        base_url=settings.payment_token_service.base_url,
        service_auth_token=settings.payment_token_service.service_auth_token,
        timeout_seconds=settings.payment_token_service.timeout_seconds,
    ) as client:
        try:
            payment_data = await client.decrypt(
                payment_token="pt_example_token_123",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )

            print(f"✅ Token decrypted successfully!")
            print(f"Card Number: {payment_data.card_number}")
            print(f"Expiration: {payment_data.exp_month}/{payment_data.exp_year}")
            print(f"Cardholder: {payment_data.cardholder_name}")

        except TokenNotFound as e:
            print(f"❌ Token not found: {e}")
            # Terminal error - send to DLQ

        except TokenExpired as e:
            print(f"❌ Token expired: {e}")
            # Terminal error - send to DLQ

        except Forbidden as e:
            print(f"❌ Unauthorized: {e}")
            # Terminal error - send to DLQ

        except ProcessorTimeout as e:
            print(f"⚠️  Service timeout: {e}")
            # Retryable error - retry with backoff


async def example_token_not_found():
    """Example: Handle token not found error."""
    print("\n=== Example 2: Token Not Found ===\n")

    async with PaymentTokenServiceClient(
        base_url=settings.payment_token_service.base_url,
        service_auth_token=settings.payment_token_service.service_auth_token,
        timeout_seconds=settings.payment_token_service.timeout_seconds,
    ) as client:
        try:
            await client.decrypt(
                payment_token="pt_nonexistent",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )
        except TokenNotFound as e:
            print(f"❌ Expected error: {e}")
            print("Action: Mark auth request as FAILED, send to DLQ")


async def example_with_retry_logic():
    """Example: Implement retry logic for transient errors."""
    print("\n=== Example 3: Retry Logic for Transient Errors ===\n")

    max_retries = 3
    retry_count = 0

    async with PaymentTokenServiceClient(
        base_url=settings.payment_token_service.base_url,
        service_auth_token=settings.payment_token_service.service_auth_token,
        timeout_seconds=settings.payment_token_service.timeout_seconds,
    ) as client:
        while retry_count < max_retries:
            try:
                payment_data = await client.decrypt(
                    payment_token="pt_example",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

                print(f"✅ Success on attempt {retry_count + 1}")
                return payment_data

            except ProcessorTimeout as e:
                retry_count += 1
                print(f"⚠️  Attempt {retry_count} failed: {e}")

                if retry_count < max_retries:
                    # Exponential backoff
                    wait_time = 2**retry_count
                    print(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    print("❌ Max retries exceeded, sending to DLQ")
                    raise

            except (TokenNotFound, TokenExpired, Forbidden) as e:
                # Terminal errors - don't retry
                print(f"❌ Terminal error: {e}")
                print("Action: Send to DLQ immediately (no retry)")
                raise


async def example_configuration():
    """Example: Different ways to configure the client."""
    print("\n=== Example 4: Client Configuration ===\n")

    # Option 1: Use settings from .env
    client1 = PaymentTokenServiceClient(
        base_url=settings.payment_token_service.base_url,
        service_auth_token=settings.payment_token_service.service_auth_token,
        timeout_seconds=settings.payment_token_service.timeout_seconds,
    )
    print(f"Client 1 (from settings): {client1.base_url}")
    await client1.close()

    # Option 2: Custom configuration (e.g., for testing)
    client2 = PaymentTokenServiceClient(
        base_url="http://localhost:8000",
        service_auth_token="test-token",
        timeout_seconds=10.0,
    )
    print(f"Client 2 (custom): {client2.base_url}")
    await client2.close()

    # Option 3: Using context manager (recommended)
    async with PaymentTokenServiceClient(
        base_url="http://localhost:8000",
        service_auth_token="test-token",
        timeout_seconds=5.0,
    ) as client3:
        print(f"Client 3 (context manager): {client3.base_url}")
        # Automatic cleanup on exit


async def main():
    """Run all examples."""
    print("=" * 60)
    print("Payment Token Service Client Usage Examples")
    print("=" * 60)

    print("\nNote: These examples will fail because there's no Payment Token")
    print("Service running. They demonstrate the API usage patterns.")

    await example_configuration()

    # The following examples would work with a real Payment Token Service
    # Uncomment to test against a running service:

    # await example_successful_decrypt()
    # await example_token_not_found()
    # await example_with_retry_logic()


if __name__ == "__main__":
    asyncio.run(main())
