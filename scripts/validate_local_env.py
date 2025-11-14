#!/usr/bin/env python3
"""
Validation script for local development environment.

This script validates that all services are properly configured and can
communicate with each other by running a simple end-to-end authorization flow.
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add tests directory to path to import helpers
tests_dir = Path(__file__).parent.parent / "tests"
sys.path.insert(0, str(tests_dir))

from e2e.helpers.http_client import (
    AuthorizationAPIClient,
    PaymentTokenServiceClient,
)
from payments.v1.authorization_pb2 import AuthStatus


async def validate_environment():
    """Validate the local development environment."""

    print("\n" + "="*60)
    print("Local Development Environment Validation")
    print("="*60)

    # Use the test restaurant ID that we configured
    restaurant_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    try:
        # Step 1: Create payment token
        print("\n[1/4] Creating payment token...")
        async with PaymentTokenServiceClient("http://localhost:8001") as token_client:
            token_response = await token_client.create_token(
                card_number="4242424242424242",
                exp_month=12,
                exp_year=2025,
                cvv="123",
                restaurant_id=str(restaurant_id),
            )
            payment_token = token_response["token_id"]
            print(f"  ✓ Payment token created: {payment_token}")

        # Step 2: Submit authorization request
        print("\n[2/4] Submitting authorization request...")
        async with AuthorizationAPIClient("http://localhost:8000") as auth_client:
            idempotency_key = str(uuid.uuid4())
            auth_response = await auth_client.authorize(
                restaurant_id=restaurant_id,
                idempotency_key=idempotency_key,
                payment_token=payment_token,
                amount_cents=5000,
                currency="USD",
                metadata={"order_id": "validation-test-001"},
            )

            auth_request_id = uuid.UUID(auth_response.auth_request_id)
            print(f"  ✓ Authorization request created: {auth_request_id}")
            print(f"  Initial status: {AuthStatus.Name(auth_response.status)}")

            # Step 3: Poll for completion
            print("\n[3/4] Polling for authorization completion...")
            print("  (This validates worker is processing SQS messages)")

            status_response = await auth_client.poll_until_complete(
                auth_request_id=auth_request_id,
                restaurant_id=restaurant_id,
                timeout=30.0,
                interval=1.0,
            )

            print(f"  ✓ Authorization completed with status: {AuthStatus.Name(status_response.status)}")

            # Step 4: Verify result
            print("\n[4/4] Verifying authorization result...")
            if status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED:
                print(f"  ✓ Status: AUTHORIZED")
                print(f"  ✓ Amount: ${status_response.result.authorized_amount_cents / 100:.2f}")
                print(f"  ✓ Processor: {status_response.result.processor_name}")
                print(f"  ✓ Auth Code: {status_response.result.authorization_code}")

                print("\n" + "="*60)
                print("✅ SUCCESS - Local environment is fully functional!")
                print("="*60)
                print("\nAll services are working correctly:")
                print("  • Payment Token Service: Encrypting card data")
                print("  • Authorization API: Accepting requests & writing to DB")
                print("  • Outbox Processor: Publishing to SQS")
                print("  • LocalStack: SQS queues operational")
                print("  • Auth Worker: Processing messages from SQS")
                print("  • PostgreSQL: All tables and migrations applied")
                print()
                return 0
            else:
                print(f"  ✗ Unexpected status: {AuthStatus.Name(status_response.status)}")
                print("\n" + "="*60)
                print("⚠️  WARNING - Authorization completed but not AUTHORIZED")
                print("="*60)
                return 1

    except asyncio.TimeoutError:
        print("\n" + "="*60)
        print("❌ TIMEOUT - Authorization did not complete within 30 seconds")
        print("="*60)
        print("\nPossible issues:")
        print("  • Worker may not be processing SQS messages")
        print("  • Check worker logs: docker logs auth-processor-worker")
        print("  • Verify LocalStack queues exist: aws --endpoint-url=http://localhost:4566 sqs list-queues")
        print()
        return 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n" + "="*60)
        print("❌ FAILED - Error during validation")
        print("="*60)
        print("\nCheck service logs:")
        print("  docker logs payment-token-service")
        print("  docker logs authorization-api-service")
        print("  docker logs auth-processor-worker")
        print()
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(validate_environment())
    sys.exit(exit_code)
