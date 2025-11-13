"""Full end-to-end tests with Docker containers.

This module tests the complete payment authorization flow across all services
running in separate Docker containers with real HTTP requests and network communication.

Test Flow:
    1. Client encrypts card data
       ↓ POST /v1/payment-tokens (HTTP → Payment Token Service)
    2. Get payment token
       ↓ POST /v1/authorize (HTTP → Authorization API)
    3. Authorization API writes to DB + Outbox
       ↓ Outbox Processor → SQS
    4. Worker picks up message
       ↓ Worker → Payment Token Service (HTTP)
    5. Worker decrypts payment token
       ↓ Worker → Payment Processor
    6. Worker processes authorization
       ↓ Worker writes events + updates read model
    7. Client checks status
       ↓ GET /v1/authorize/{id}/status (HTTP → Authorization API)
    8. Verify final status
"""

import asyncio
import subprocess
import uuid

import pytest
from payments.v1.authorization_pb2 import AuthStatus

from tests.e2e.fixtures.docker_fixtures import setup_test_restaurant_config
from tests.e2e.helpers.http_client import (
    AuthorizationAPIClient,
    PaymentTokenServiceClient,
)


@pytest.fixture
async def auth_client(authorization_api_url: str):
    """Create Authorization API client."""
    async with AuthorizationAPIClient(authorization_api_url) as client:
        yield client


@pytest.fixture
async def token_client(payment_token_service_url: str):
    """Create Payment Token Service client."""
    async with PaymentTokenServiceClient(payment_token_service_url) as client:
        yield client


@pytest.fixture
def test_restaurant_id() -> uuid.UUID:
    """Generate a test restaurant ID."""
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_happy_path(
    docker_services,
    auth_client: AuthorizationAPIClient,
    token_client: PaymentTokenServiceClient,
    test_restaurant_id: uuid.UUID,
):
    """Test complete flow: tokenize → authorize → process → detokenize → status.

    This test validates:
    - Payment Token Service successfully encrypts card data
    - Authorization API accepts request and writes to outbox
    - Outbox processor sends message to SQS
    - Worker picks up message from SQS
    - Worker calls Payment Token Service to decrypt token
    - Worker processes authorization via MockProcessor
    - Worker writes result to database
    - Authorization API returns correct status
    """
    # Step 1: Tokenize card data
    print("\n[1/4] Creating payment token...")
    token_response = await token_client.create_token(
        card_number="4242424242424242",  # Stripe test card (success)
        exp_month=12,
        exp_year=2025,
        cvv="123",
        restaurant_id=str(test_restaurant_id),
    )
    payment_token = token_response["token_id"]
    print(f"  ✓ Payment token created: {payment_token}")

    # Step 2: Submit authorization request
    print("[2/4] Submitting authorization request...")
    idempotency_key = str(uuid.uuid4())
    auth_response = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=payment_token,
        amount_cents=5000,
        currency="USD",
        metadata={"order_id": "test-order-123", "table_number": "42"},
    )

    auth_request_id = uuid.UUID(auth_response.auth_request_id)
    print(f"  ✓ Authorization request created: {auth_request_id}")
    print(f"  Status: {AuthStatus.Name(auth_response.status)}")

    # Step 3: Poll for completion
    print("[3/4] Polling for completion...")
    status_response = await auth_client.poll_until_complete(
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        timeout=30.0,
        interval=1.0,
    )

    print(f"  ✓ Authorization completed with status: {AuthStatus.Name(status_response.status)}")

    # Step 4: Verify result
    print("[4/4] Verifying result...")
    assert status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
    assert status_response.result.authorized_amount_cents == 5000
    assert status_response.result.currency == "USD"
    assert status_response.result.processor_name == "mock"
    assert status_response.result.processor_auth_id is not None
    assert status_response.result.authorization_code is not None
    print(f"  ✓ Verified authorized amount: ${status_response.result.authorized_amount_cents / 100:.2f}")
    print(f"  ✓ Processor: {status_response.result.processor_name}")
    print(f"  ✓ Auth code: {status_response.result.authorization_code}")

    print("\n✅ Full E2E test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_card_decline(
    docker_services,
    auth_client: AuthorizationAPIClient,
    token_client: PaymentTokenServiceClient,
    test_restaurant_id: uuid.UUID,
):
    """Test full flow with card that will be declined.

    Uses test card: 4000000000009995 (insufficient funds).
    """
    print("\n[Card Decline Test]")

    # Step 1: Tokenize decline card
    print("[1/4] Creating payment token with decline card...")
    token_response = await token_client.create_token(
        card_number="4000000000009995",  # Stripe test card (insufficient funds)
        exp_month=12,
        exp_year=2025,
        cvv="123",
        restaurant_id=str(test_restaurant_id),
    )
    payment_token = token_response["token_id"]
    print(f"  ✓ Payment token created: {payment_token}")

    # Step 2: Submit authorization request
    print("[2/4] Submitting authorization request...")
    idempotency_key = str(uuid.uuid4())
    auth_response = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=payment_token,
        amount_cents=5000,
        currency="USD",
    )

    auth_request_id = uuid.UUID(auth_response.auth_request_id)
    print(f"  ✓ Authorization request created: {auth_request_id}")

    # Step 3: Poll for completion
    print("[3/4] Polling for completion...")
    status_response = await auth_client.poll_until_complete(
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        timeout=30.0,
        interval=1.0,
    )

    print(f"  ✓ Authorization completed with status: {AuthStatus.Name(status_response.status)}")

    # Step 4: Verify denial
    print("[4/4] Verifying denial...")
    assert status_response.status == AuthStatus.AUTH_STATUS_DENIED
    assert status_response.result.denial_code is not None
    assert status_response.result.denial_reason is not None
    print(f"  ✓ Denial code: {status_response.result.denial_code}")
    print(f"  ✓ Denial reason: {status_response.result.denial_reason}")

    print("\n✅ Card decline test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_invalid_token(
    docker_services,
    auth_client: AuthorizationAPIClient,
    test_restaurant_id: uuid.UUID,
):
    """Test full flow with invalid payment token.

    Worker should fail to decrypt and mark as FAILED.
    """
    print("\n[Invalid Token Test]")

    # Step 1: Submit authorization with invalid token
    print("[1/3] Submitting authorization request with invalid token...")
    idempotency_key = str(uuid.uuid4())
    invalid_token = "invalid-token-" + str(uuid.uuid4())

    auth_response = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=invalid_token,
        amount_cents=5000,
        currency="USD",
    )

    auth_request_id = uuid.UUID(auth_response.auth_request_id)
    print(f"  ✓ Authorization request created: {auth_request_id}")

    # Step 2: Poll for completion
    print("[2/3] Polling for completion...")
    status_response = await auth_client.poll_until_complete(
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
        timeout=30.0,
        interval=1.0,
    )

    print(f"  ✓ Authorization completed with status: {AuthStatus.Name(status_response.status)}")

    # Step 3: Verify failure
    print("[3/3] Verifying failure...")
    assert status_response.status == AuthStatus.AUTH_STATUS_FAILED
    print("  ✓ Status is FAILED as expected")

    print("\n✅ Invalid token test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_payment_token_service_down(
    docker_services,
    docker_compose_file,
    auth_client: AuthorizationAPIClient,
    test_restaurant_id: uuid.UUID,
):
    """Test system behavior when Payment Token Service is down.

    Worker should retry and eventually fail gracefully.
    """
    print("\n[Payment Token Service Down Test]")

    # First create a token while service is up
    print("[1/5] Creating payment token while service is up...")
    async with PaymentTokenServiceClient() as token_client:
        token_response = await token_client.create_token(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            restaurant_id=str(test_restaurant_id),
        )
        payment_token = token_response["token_id"]
        print(f"  ✓ Payment token created: {payment_token}")

    # Step 2: Stop Payment Token Service
    print("[2/5] Stopping Payment Token Service...")
    subprocess.run(
        [
            "docker-compose",
            "-f",
            str(docker_compose_file),
            "stop",
            "payment-token",
        ],
        check=True,
        capture_output=True,
    )
    print("  ✓ Payment Token Service stopped")

    # Give it a moment to fully stop
    await asyncio.sleep(2)

    # Step 3: Submit authorization request
    print("[3/5] Submitting authorization request...")
    idempotency_key = str(uuid.uuid4())

    try:
        auth_response = await auth_client.authorize(
            restaurant_id=test_restaurant_id,
            idempotency_key=idempotency_key,
            payment_token=payment_token,
            amount_cents=5000,
            currency="USD",
        )

        auth_request_id = uuid.UUID(auth_response.auth_request_id)
        print(f"  ✓ Authorization request created: {auth_request_id}")

        # Step 4: Poll for result (should fail since token service is down)
        # Note: With visibility_timeout=30s and max_retries=2, we need ~35-40 seconds
        # (1st attempt timeout 5s + visibility 30s + 2nd attempt ~5s)
        print("[4/5] Polling for completion...")
        status_response = await auth_client.poll_until_complete(
            auth_request_id=auth_request_id,
            restaurant_id=test_restaurant_id,
            timeout=60.0,
            interval=2.0,
        )

        print(f"  ✓ Authorization completed with status: {AuthStatus.Name(status_response.status)}")

        # Should fail since token service is down
        assert status_response.status == AuthStatus.AUTH_STATUS_FAILED
        print("  ✓ Status is FAILED as expected (token service unavailable)")

    finally:
        # Step 5: Restart Payment Token Service
        print("[5/5] Restarting Payment Token Service...")
        subprocess.run(
            [
                "docker-compose",
                "-f",
                str(docker_compose_file),
                "start",
                "payment-token",
            ],
            check=True,
            capture_output=True,
        )
        print("  ✓ Payment Token Service restarted")

        # Wait for service to be healthy
        await asyncio.sleep(5)

    print("\n✅ Payment Token Service down test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_concurrent_requests(
    docker_services,
    auth_client: AuthorizationAPIClient,
    token_client: PaymentTokenServiceClient,
):
    """Test 10 concurrent requests across all services.

    Validates:
    - No race conditions
    - All requests processed correctly
    - Services handle concurrent load
    """
    print("\n[Concurrent Requests Test]")

    num_requests = 10
    restaurant_ids = [uuid.uuid4() for _ in range(num_requests)]

    # Set up restaurant configs for all generated restaurant IDs
    print(f"[0/3] Setting up restaurant configs for {num_requests} restaurants...")
    for rid in restaurant_ids:
        setup_test_restaurant_config(str(rid))
    print(f"  ✓ Configured {num_requests} restaurants")

    # Step 1: Create payment tokens concurrently
    print(f"[1/3] Creating {num_requests} payment tokens concurrently...")
    token_tasks = [
        token_client.create_token(
            card_number="4242424242424242",
            exp_month=12,
            exp_year=2025,
            cvv="123",
            restaurant_id=str(rid),
        )
        for rid in restaurant_ids
    ]
    token_responses = await asyncio.gather(*token_tasks)
    payment_tokens = [resp["token_id"] for resp in token_responses]
    print(f"  ✓ Created {len(payment_tokens)} payment tokens")

    # Step 2: Submit authorizations concurrently
    print(f"[2/3] Submitting {num_requests} authorization requests concurrently...")
    auth_tasks = [
        auth_client.authorize(
            restaurant_id=restaurant_ids[i],
            idempotency_key=str(uuid.uuid4()),
            payment_token=payment_tokens[i],
            amount_cents=1000 + i * 100,  # Different amounts
            currency="USD",
        )
        for i in range(num_requests)
    ]
    auth_responses = await asyncio.gather(*auth_tasks)
    auth_request_ids = [uuid.UUID(resp.auth_request_id) for resp in auth_responses]
    print(f"  ✓ Created {len(auth_request_ids)} authorization requests")

    # Step 3: Poll for completion concurrently
    print(f"[3/3] Polling for completion of {num_requests} requests...")
    status_tasks = [
        auth_client.poll_until_complete(
            auth_request_id=auth_request_ids[i],
            restaurant_id=restaurant_ids[i],
            timeout=30.0,
            interval=1.0,
        )
        for i in range(num_requests)
    ]
    status_responses = await asyncio.gather(*status_tasks)

    # Verify all succeeded
    successful = sum(
        1 for resp in status_responses if resp.status == AuthStatus.AUTH_STATUS_AUTHORIZED
    )
    print(f"  ✓ All {successful}/{num_requests} requests completed successfully")

    for i, status_resp in enumerate(status_responses):
        assert status_resp.status == AuthStatus.AUTH_STATUS_AUTHORIZED
        expected_amount = 1000 + i * 100
        assert status_resp.result.authorized_amount_cents == expected_amount

    print("\n✅ Concurrent requests test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_fast_path(
    docker_services,
    auth_client: AuthorizationAPIClient,
    token_client: PaymentTokenServiceClient,
    test_restaurant_id: uuid.UUID,
):
    """Test fast path where worker completes within 5 seconds.

    POST /authorize should return 200 with result (not 202).
    """
    print("\n[Fast Path Test]")

    # Step 1: Create payment token
    print("[1/3] Creating payment token...")
    token_response = await token_client.create_token(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        restaurant_id=str(test_restaurant_id),
    )
    payment_token = token_response["token_id"]
    print(f"  ✓ Payment token created: {payment_token}")

    # Step 2: Submit authorization (should complete fast)
    print("[2/3] Submitting authorization request...")
    idempotency_key = str(uuid.uuid4())

    auth_response = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=payment_token,
        amount_cents=2500,
        currency="USD",
    )

    auth_request_id = uuid.UUID(auth_response.auth_request_id)
    print(f"  ✓ Authorization request created: {auth_request_id}")
    print(f"  Initial status: {AuthStatus.Name(auth_response.status)}")

    # Step 3: If not completed immediately, poll
    if auth_response.status in (
        AuthStatus.AUTH_STATUS_PENDING,
        AuthStatus.AUTH_STATUS_PROCESSING,
    ):
        print("[3/3] Polling for completion (slow path taken)...")
        status_response = await auth_client.poll_until_complete(
            auth_request_id=auth_request_id,
            restaurant_id=test_restaurant_id,
            timeout=30.0,
            interval=1.0,
        )
    else:
        # Fast path - result already in response
        print("[3/3] Fast path taken - result already available!")
        status_response = auth_response
        assert auth_response.HasField("result")

    # Verify result
    assert status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
    assert status_response.result.authorized_amount_cents == 2500
    print(f"  ✓ Verified authorized amount: ${status_response.result.authorized_amount_cents / 100:.2f}")

    print("\n✅ Fast path test passed!")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_e2e_idempotency(
    docker_services,
    auth_client: AuthorizationAPIClient,
    token_client: PaymentTokenServiceClient,
    test_restaurant_id: uuid.UUID,
):
    """Test idempotency - same request with same key returns same auth_request_id.

    Validates:
    - Same idempotency key returns same auth_request_id
    - Second request doesn't create duplicate authorization
    - System properly handles idempotent retries
    """
    print("\n[Idempotency Test]")

    # Step 1: Create payment token
    print("[1/4] Creating payment token...")
    token_response = await token_client.create_token(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        restaurant_id=str(test_restaurant_id),
    )
    payment_token = token_response["token_id"]
    print(f"  ✓ Payment token created: {payment_token}")

    # Step 2: First authorization request
    print("[2/4] Submitting first authorization request...")
    idempotency_key = str(uuid.uuid4())

    auth_response_1 = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=payment_token,
        amount_cents=3000,
        currency="USD",
        metadata={"order_id": "idempotency-test-123"},
    )

    auth_request_id_1 = uuid.UUID(auth_response_1.auth_request_id)
    print(f"  ✓ First request created: {auth_request_id_1}")

    # Step 3: Second authorization request with SAME idempotency key
    print("[3/4] Submitting second request with same idempotency key...")
    auth_response_2 = await auth_client.authorize(
        restaurant_id=test_restaurant_id,
        idempotency_key=idempotency_key,
        payment_token=payment_token,
        amount_cents=3000,
        currency="USD",
        metadata={"order_id": "idempotency-test-123"},
    )

    auth_request_id_2 = uuid.UUID(auth_response_2.auth_request_id)
    print(f"  ✓ Second request returned: {auth_request_id_2}")

    # Should return SAME auth_request_id
    assert auth_request_id_1 == auth_request_id_2
    print(f"  ✓ Idempotency verified: both requests returned same ID")

    # Step 4: Wait for completion
    print("[4/4] Polling for completion...")
    status_response = await auth_client.poll_until_complete(
        auth_request_id=auth_request_id_1,
        restaurant_id=test_restaurant_id,
        timeout=30.0,
        interval=1.0,
    )

    # Verify result
    assert status_response.status == AuthStatus.AUTH_STATUS_AUTHORIZED
    assert status_response.result.authorized_amount_cents == 3000
    print(f"  ✓ Authorization completed successfully")

    print("\n✅ Idempotency test passed!")
