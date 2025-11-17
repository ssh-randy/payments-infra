"""End-to-end tests for API Partner Key encryption flow.

These tests verify the complete API partner key flow through the HTTP API:
- Creating payment tokens with encryption_metadata
- Backward compatibility with BDK flow
- Error handling for invalid key_ids
- Internal decrypt API with API partner tokens
"""

import base64
import os
import uuid

import httpx
import pytest
from payments_proto.payments.v1 import payment_token_pb2

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Test configuration
SERVICE_URL = "http://localhost:8002"
API_KEY = "test-api-key-12345"
INTERNAL_SERVICE_TOKEN = "service:auth-processor-worker"

# Primary encryption key (must match what's set in docker-compose or env)
PRIMARY_KEY_HEX = "0123456789abcdef" * 4
PRIMARY_KEY = bytes.fromhex(PRIMARY_KEY_HEX)


@pytest.mark.e2e
class TestAPIPartnerKeyE2E:
    """End-to-end tests for API partner key flow via HTTP API."""

    def encrypt_payment_data_with_primary_key(self, payment_data_dict):
        """Encrypt payment data using primary key (simulating frontend)."""
        import json

        # Serialize payment data as JSON
        payment_data_bytes = json.dumps(payment_data_dict).encode('utf-8')

        # Encrypt with AES-256-GCM
        aesgcm = AESGCM(PRIMARY_KEY)
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = aesgcm.encrypt(nonce, payment_data_bytes, None)

        return ciphertext, nonce

    def test_create_token_with_api_partner_key(self, docker_services):
        """Test creating payment token with API partner encryption metadata."""
        # Create payment data
        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "John Doe"
        }

        # Encrypt with primary key
        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        # Create JSON request with encryption_metadata
        restaurant_id = str(uuid.uuid4())
        json_request = {
            "restaurant_id": restaurant_id,
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "primary",
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            },
            "metadata": {"card_brand": "visa", "last4": "9012"}
        }

        # Send request
        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        # Verify response
        assert response.status_code == 201

        # Parse JSON response
        json_response = response.json()

        assert json_response["payment_token"].startswith("pt_")
        assert json_response["restaurant_id"] == restaurant_id
        assert json_response["metadata"]["card_brand"] == "visa"
        assert json_response["metadata"]["last4"] == "9012"

    def test_create_token_with_demo_primary_key_001(self, docker_services):
        """Test that demo-primary-key-001 key_id also works."""
        payment_data = {
            "card_number": "4111111111111111",
            "exp_month": "06",
            "exp_year": "2026",
            "cvv": "456",
            "cardholder_name": "Jane Smith"
        }

        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        # Create JSON request
        json_request = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "demo-primary-key-001",  # Alternative key_id
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            }
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert response.status_code == 201

        json_response = response.json()

        assert json_response["payment_token"].startswith("pt_")

    def test_create_token_with_invalid_algorithm_fails(self, docker_services):
        """Test that unsupported algorithm returns error."""
        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test User"
        }

        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        request_json = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "primary",
                "algorithm": "AES-128-CBC",  # Unsupported
                "iv": base64.b64encode(nonce).decode()
            }
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=request_json,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert response.status_code == 400  # Bad request

    def test_create_token_with_unknown_key_id_fails(self, docker_services):
        """Test that unknown key_id returns error."""
        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test User"
        }

        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        request_json = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "unknown-key-id-12345",  # Unknown
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            }
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=request_json,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert response.status_code in [400, 500]  # Bad request or internal error

    def test_create_token_with_wrong_encryption_key_fails(self, docker_services):
        """Test that data encrypted with wrong key fails to decrypt."""
        import json

        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test User"
        }

        # Encrypt with WRONG key
        wrong_key = os.urandom(32)
        payment_data_bytes = json.dumps(payment_data).encode('utf-8')
        aesgcm = AESGCM(wrong_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, payment_data_bytes, None)

        json_request = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "primary",  # Correct key_id but data encrypted with wrong key
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            }
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert response.status_code == 400  # Decryption should fail

    def test_create_token_without_device_token_or_encryption_metadata_fails(self, docker_services):
        """Test that request without both device_token and encryption_metadata fails."""
        json_request = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(b"fake data").decode()
            # No device_token, no encryption_metadata
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert response.status_code == 400  # Should require one or the other

    def test_decrypt_api_partner_token_via_internal_api(self, docker_services):
        """Test decrypting an API partner token via internal decrypt API."""
        # Create payment data
        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "John Doe"
        }

        # Create token with API partner key
        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        restaurant_id = str(uuid.uuid4())
        json_request = {
            "restaurant_id": restaurant_id,
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "primary",
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            }
        }

        create_response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        assert create_response.status_code == 201

        create_json_response = create_response.json()
        payment_token = create_json_response["payment_token"]

        # Decrypt via internal API
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=payment_token,
            restaurant_id=restaurant_id,
            requesting_service="auth-processor-worker"
        )

        decrypt_response = httpx.post(
            f"{SERVICE_URL}/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "X-Service-Auth": INTERNAL_SERVICE_TOKEN,
                "X-Request-ID": str(uuid.uuid4()),
                "Content-Type": "application/x-protobuf"
            },
            timeout=10.0
        )

        assert decrypt_response.status_code == 200

        # Verify decrypted data
        decrypt_response_pb = payment_token_pb2.DecryptPaymentTokenResponse()
        decrypt_response_pb.ParseFromString(decrypt_response.content)

        assert decrypt_response_pb.payment_data.card_number == "4532123456789012"
        assert decrypt_response_pb.payment_data.exp_month == "12"
        assert decrypt_response_pb.payment_data.exp_year == "2025"
        assert decrypt_response_pb.payment_data.cvv == "123"
        assert decrypt_response_pb.payment_data.cardholder_name == "John Doe"

    def test_idempotency_with_api_partner_key(self, docker_services):
        """Test that idempotency works with API partner key flow."""
        payment_data = {
            "card_number": "4532123456789012",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test User"
        }

        ciphertext, nonce = self.encrypt_payment_data_with_primary_key(payment_data)

        idempotency_key = f"test-idempotency-{uuid.uuid4()}"
        restaurant_id = str(uuid.uuid4())

        json_request = {
            "restaurant_id": restaurant_id,
            "encrypted_payment_data": base64.b64encode(ciphertext).decode(),
            "encryption_metadata": {
                "key_id": "primary",
                "algorithm": "AES-256-GCM",
                "iv": base64.b64encode(nonce).decode()
            }
        }

        # First request
        response1 = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "X-Idempotency-Key": idempotency_key
            },
            timeout=10.0
        )

        assert response1.status_code == 201

        json_response1 = response1.json()
        token1 = json_response1["payment_token"]

        # Second request with same idempotency key
        response2 = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "X-Idempotency-Key": idempotency_key
            },
            timeout=10.0
        )

        assert response2.status_code == 200  # Returns existing token

        json_response2 = response2.json()
        token2 = json_response2["payment_token"]

        # Should return same token
        assert token1 == token2


@pytest.mark.e2e
class TestBDKFlowBackwardCompatibility:
    """Tests to verify BDK flow still works (backward compatibility)."""

    def test_bdk_flow_still_works(self, docker_services):
        """Test that original BDK flow continues to work alongside API partner flow."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        # Simulate BDK flow
        bdk = b"0" * 32  # LocalStack returns deterministic key
        device_token = "test-device-12345"

        # Derive device key
        info = b"payment-token-v1:" + device_token.encode("utf-8")
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=info
        )
        device_key = hkdf.derive(bdk)

        # Create payment data
        payment_data = payment_token_pb2.PaymentData(
            card_number="4111111111111111",
            exp_month="06",
            exp_year="2026",
            cvv="456",
            cardholder_name="BDK User"
        )

        # Encrypt with device key
        payment_data_bytes = payment_data.SerializeToString()
        aesgcm = AESGCM(device_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, payment_data_bytes, None)

        # Format as device would send it (nonce + ciphertext)
        device_encrypted_data = nonce + ciphertext

        # Create JSON request with device_token (BDK flow)
        json_request = {
            "restaurant_id": str(uuid.uuid4()),
            "encrypted_payment_data": base64.b64encode(device_encrypted_data).decode(),
            "device_token": device_token  # BDK flow uses device_token
            # No encryption_metadata
        }

        response = httpx.post(
            f"{SERVICE_URL}/v1/payment-tokens",
            json=json_request,
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            timeout=10.0
        )

        # Should still work
        assert response.status_code == 201

        json_response = response.json()

        assert json_response["payment_token"].startswith("pt_")
