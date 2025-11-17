"""Pytest configuration and fixtures for E2E tests.

This module provides fixtures for black-box testing of the Payment Token Service
running in Docker. Tests interact with the service via HTTP API only.
"""

import base64
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Generator

import httpx
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Import protobuf messages
import sys
sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python')
from payments_proto.payments.v1 import payment_token_pb2

# Test configuration
SERVICE_URL = "http://localhost:8002"
API_KEY = "test-api-key-12345"
INTERNAL_SERVICE_TOKEN = "service:auth-processor-worker"
TEST_BDK = b"0" * 32  # LocalStack KMS will return this deterministic key


@pytest.fixture(scope="session")
def docker_services():
    """Start Docker services for testing and tear them down after tests.

    This fixture:
    1. Starts all services via docker-compose
    2. Waits for service health checks
    3. Yields control to tests
    4. Tears down services after all tests complete
    """
    compose_file = Path(__file__).parent / "docker-compose.test.yml"

    # Start services
    print("\n🚀 Starting Docker services for E2E tests...")
    subprocess.run(
        ["docker-compose", "-f", str(compose_file), "up", "-d", "--build"],
        check=True,
        capture_output=True,
    )

    # Wait for service to be healthy
    print("⏳ Waiting for services to be healthy...")
    max_retries = 30
    for i in range(max_retries):
        try:
            response = httpx.get(f"{SERVICE_URL}/health", timeout=2.0)
            if response.status_code == 200:
                print("✅ Payment Token Service is healthy")
                break
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            if i == max_retries - 1:
                # Print logs if service didn't start
                subprocess.run(
                    ["docker-compose", "-f", str(compose_file), "logs"],
                    check=False,
                )
                raise RuntimeError("Payment Token Service failed to become healthy")
            time.sleep(2)

    # Wait a bit more for database migrations to complete
    time.sleep(3)

    yield

    # Teardown: stop and remove containers
    print("\n🧹 Cleaning up Docker services...")
    subprocess.run(
        ["docker-compose", "-f", str(compose_file), "down", "-v"],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="function")
def api_client(docker_services) -> httpx.Client:
    """Provide HTTP client for API requests.

    Returns:
        Configured httpx.Client with base URL and default headers
    """
    return httpx.Client(
        base_url=SERVICE_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
        },
        timeout=10.0,
    )


@pytest.fixture(scope="function")
def internal_api_client(docker_services) -> httpx.Client:
    """Provide HTTP client for internal API requests.

    Returns:
        Configured httpx.Client for internal endpoints
    """
    return httpx.Client(
        base_url=SERVICE_URL,
        timeout=10.0,
    )


@pytest.fixture
def test_restaurant_id() -> str:
    """Generate unique restaurant ID for each test."""
    return str(uuid.uuid4())


@pytest.fixture
def test_device_token() -> str:
    """Generate unique device token for each test."""
    return f"device_{uuid.uuid4().hex[:16]}"


@pytest.fixture
def idempotency_key() -> str:
    """Generate unique idempotency key for each test."""
    return str(uuid.uuid4())


def derive_device_key(bdk: bytes, device_token: str) -> bytes:
    """Derive device-specific encryption key from BDK.

    This matches the key derivation in the service implementation.

    Args:
        bdk: Base Derivation Key (32 bytes)
        device_token: Device identifier

    Returns:
        32-byte AES-256 key
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"payment-token-v1:" + device_token.encode('utf-8'),
        backend=default_backend()
    ).derive(bdk)


def encrypt_payment_data(payment_data: dict[str, Any], device_token: str) -> bytes:
    """Encrypt payment data as if it came from a POS device.

    This simulates the POS device encryption using device-derived keys.

    Args:
        payment_data: Payment data dictionary (card_number, exp_month, etc.)
        device_token: Device identifier for key derivation

    Returns:
        Encrypted payment data (bytes)
    """
    # Derive device key
    device_key = derive_device_key(TEST_BDK, device_token)

    # Create PaymentData protobuf message
    pb_payment_data = payment_token_pb2.PaymentData(
        card_number=payment_data.get("card_number", "4532015112830366"),
        exp_month=payment_data.get("exp_month", "12"),
        exp_year=payment_data.get("exp_year", "2025"),
        cvv=payment_data.get("cvv", "123"),
        cardholder_name=payment_data.get("cardholder_name", "Test Cardholder"),
    )

    # Add billing address if provided
    if "billing_address" in payment_data:
        addr = payment_data["billing_address"]
        pb_payment_data.billing_address.CopyFrom(
            payment_token_pb2.Address(
                line1=addr.get("line1", ""),
                line2=addr.get("line2", ""),
                city=addr.get("city", ""),
                state=addr.get("state", ""),
                postal_code=addr.get("postal_code", ""),
                country=addr.get("country", "US"),
            )
        )

    # Serialize to bytes
    plaintext = pb_payment_data.SerializeToString()

    # Encrypt with AES-GCM
    aesgcm = AESGCM(device_key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Return nonce + ciphertext (same format as production)
    return nonce + ciphertext


@pytest.fixture
def create_token_helper(api_client, test_restaurant_id, test_device_token, idempotency_key):
    """Helper function to create payment tokens.

    Returns:
        Function that creates a token with optional custom parameters
    """
    def _create_token(
        payment_data: dict[str, Any] | None = None,
        restaurant_id: str | None = None,
        device_token: str | None = None,
        idempotency_key_override: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Create a payment token via API.

        Args:
            payment_data: Custom payment data (uses default if None)
            restaurant_id: Restaurant ID (uses fixture value if None)
            device_token: Device token (uses fixture value if None)
            idempotency_key_override: Custom idempotency key (uses fixture value if None)
            metadata: Optional metadata dictionary

        Returns:
            HTTP response from create token endpoint
        """
        # Use defaults if not provided
        restaurant_id = restaurant_id or test_restaurant_id
        device_token = device_token or test_device_token
        idempotency_key_value = idempotency_key_override or idempotency_key

        # Use default payment data if not provided
        if payment_data is None:
            payment_data = {
                "card_number": "4532015112830366",
                "exp_month": "12",
                "exp_year": "2025",
                "cvv": "123",
                "cardholder_name": "Test Cardholder",
            }

        # Encrypt payment data
        encrypted_data = encrypt_payment_data(payment_data, device_token)

        # Create JSON request
        json_request = {
            "restaurant_id": restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": device_token,
            "idempotency_key": idempotency_key_value,
        }

        if metadata:
            json_request["metadata"] = metadata

        # Send request
        return api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key_value,
            },
        )

    return _create_token


@pytest.fixture
def unauthorized_service_client(docker_services) -> httpx.Client:
    """Provide HTTP client for testing unauthorized service access.

    Returns:
        Configured httpx.Client with unauthorized service credentials
    """
    return httpx.Client(
        base_url=SERVICE_URL,
        timeout=10.0,
    )


@pytest.fixture
def encrypt_payment_data_fn():
    """Provide function to encrypt payment data for testing.

    Returns:
        Function that encrypts payment data with device token
    """
    def _encrypt(payment_data: dict[str, Any], device_token: str) -> bytes:
        return encrypt_payment_data(payment_data, device_token)

    return _encrypt
