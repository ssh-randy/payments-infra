"""HTTP client helpers for E2E tests.

This module provides real HTTP client helpers (not ASGI) for testing
services running in Docker containers.
"""

import asyncio
import base64
import os
import uuid
from typing import Any, Optional

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Import payment token protobuf (still needed for encrypting card data for device simulation)
from payments_proto.payments.v1 import payment_token_pb2

# Test configuration
TEST_API_KEY = "test-api-key-12345"
TEST_BDK = b"0" * 32  # LocalStack KMS returns this deterministic key


class AuthorizationAPIClient:
    """Async HTTP client for Authorization API service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the client.

        Args:
            base_url: Base URL of the Authorization API service
        """
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> "AuthorizationAPIClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def health_check(self) -> dict[str, Any]:
        """Check service health.

        Returns:
            Health check response

        Raises:
            httpx.HTTPError: If request fails
        """
        response = await self.client.get("/health")
        response.raise_for_status()
        return response.json()

    async def authorize(
        self,
        restaurant_id: uuid.UUID,
        idempotency_key: str,
        payment_token: str,
        amount_cents: int,
        currency: str = "USD",
        metadata: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Submit authorization request.

        Args:
            restaurant_id: Restaurant UUID
            idempotency_key: Idempotency key for request
            payment_token: Payment token from Payment Token Service
            amount_cents: Amount in cents
            currency: Currency code (default: USD)
            metadata: Optional metadata dictionary

        Returns:
            JSON response dict with auth_request_id, status, and optionally result

        Raises:
            httpx.HTTPError: If request fails
        """
        # Build JSON request
        request_data = {
            "restaurant_id": str(restaurant_id),
            "idempotency_key": idempotency_key,
            "payment_token": payment_token,
            "amount_cents": amount_cents,
            "currency": currency,
            "metadata": metadata or {},
        }

        # Send request
        response = await self.client.post(
            "/v1/authorize",
            json=request_data,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        # Parse and return JSON response
        return response.json()

    async def get_status(
        self, auth_request_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> dict[str, Any]:
        """Get authorization status.

        Args:
            auth_request_id: Authorization request UUID
            restaurant_id: Restaurant UUID

        Returns:
            JSON response dict with auth_request_id, status, created_at, updated_at, and optionally result

        Raises:
            httpx.HTTPError: If request fails
        """
        response = await self.client.get(
            f"/v1/authorize/{auth_request_id}/status",
            params={"restaurant_id": str(restaurant_id)},
        )
        response.raise_for_status()

        # Parse and return JSON response
        return response.json()

    async def poll_until_complete(
        self,
        auth_request_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        timeout: float = 30.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        """Poll status until authorization completes.

        Args:
            auth_request_id: Authorization request UUID
            restaurant_id: Restaurant UUID
            timeout: Maximum time to poll in seconds
            interval: Time between polls in seconds

        Returns:
            JSON response dict when complete

        Raises:
            TimeoutError: If authorization doesn't complete within timeout
        """
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            status = await self.get_status(auth_request_id, restaurant_id)

            # Check if completed (status values are strings: "AUTHORIZED", "DENIED", "FAILED")
            if status["status"] in ("AUTHORIZED", "DENIED", "FAILED"):
                return status

            await asyncio.sleep(interval)

        raise TimeoutError(
            f"Authorization {auth_request_id} did not complete within {timeout}s"
        )


def _derive_device_key(bdk: bytes, device_token: str) -> bytes:
    """Derive device-specific encryption key from BDK.

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


def _encrypt_card_data(
    card_number: str,
    exp_month: int,
    exp_year: int,
    cvv: str,
    device_token: str,
    cardholder_name: Optional[str] = None,
) -> bytes:
    """Encrypt card data as if it came from a POS device.

    Args:
        card_number: Credit card number
        exp_month: Expiration month (1-12)
        exp_year: Expiration year (4 digits)
        cvv: Card CVV
        device_token: Device identifier for key derivation
        cardholder_name: Optional cardholder name

    Returns:
        Encrypted payment data (nonce + ciphertext)
    """
    # Derive device key
    device_key = _derive_device_key(TEST_BDK, device_token)

    # Create PaymentData protobuf message
    pb_payment_data = payment_token_pb2.PaymentData(
        card_number=card_number,
        exp_month=str(exp_month),
        exp_year=str(exp_year),
        cvv=cvv,
        cardholder_name=cardholder_name or "Test Cardholder",
    )

    # Serialize to bytes
    plaintext = pb_payment_data.SerializeToString()

    # Encrypt with AES-GCM
    aesgcm = AESGCM(device_key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Return nonce + ciphertext (same format as production)
    return nonce + ciphertext


class PaymentTokenServiceClient:
    """Async HTTP client for Payment Token Service."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        """Initialize the client.

        Args:
            base_url: Base URL of the Payment Token Service
        """
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {TEST_API_KEY}"}
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> "PaymentTokenServiceClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def health_check(self) -> dict[str, Any]:
        """Check service health.

        Returns:
            Health check response

        Raises:
            httpx.HTTPError: If request fails
        """
        response = await self.client.get("/health")
        response.raise_for_status()
        return response.json()

    async def create_token(
        self,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        cardholder_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a payment token.

        Args:
            card_number: Credit card number
            exp_month: Expiration month (1-12)
            exp_year: Expiration year (4 digits)
            cvv: Card CVV
            cardholder_name: Optional cardholder name
            restaurant_id: Optional restaurant ID (generates one if not provided)

        Returns:
            Token creation response with payment_token

        Raises:
            httpx.HTTPError: If request fails
        """
        # Generate device token and restaurant ID if not provided
        device_token = f"device_{uuid.uuid4().hex[:16]}"
        restaurant_id = restaurant_id or str(uuid.uuid4())
        idempotency_key = str(uuid.uuid4())

        # Encrypt card data as device would
        encrypted_payment_data = _encrypt_card_data(
            card_number=card_number,
            exp_month=exp_month,
            exp_year=exp_year,
            cvv=cvv,
            device_token=device_token,
            cardholder_name=cardholder_name,
        )

        # Build JSON request
        request_data = {
            "restaurant_id": restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_payment_data).decode("utf-8"),
            "device_token": device_token,
            "metadata": {},
        }

        # Send request
        response = await self.client.post(
            "/v1/payment-tokens",
            json=request_data,
            headers={
                "Content-Type": "application/json",
                "X-Idempotency-Key": idempotency_key,
            },
        )
        response.raise_for_status()

        # Parse JSON response
        json_response = response.json()

        # Return as dict for compatibility with existing tests
        return {
            "token_id": json_response["payment_token"],
            "restaurant_id": json_response["restaurant_id"],
            "expires_at": json_response["expires_at"],
        }
