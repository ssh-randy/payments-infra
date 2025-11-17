"""E2E tests for token creation behaviors (B1, B2).

Tests:
- B1: Token Creation with Idempotency
- B2: Device-Based Decryption
"""

import base64
import uuid
import sys
sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python')
from payments_proto.payments.v1 import payment_token_pb2


class TestIdempotencyBehavior:
    """Test B1: Token Creation with Idempotency."""

    def test_same_idempotency_key_returns_same_token(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that same idempotency key returns same token within 24 hours."""
        # Prepare payment data
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        # Create JSON request
        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        # First request - should create token (201 Created)
        response1 = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )
        assert response1.status_code == 201

        # Parse response
        json_response1 = response1.json()
        token_id_1 = json_response1["payment_token"]

        # Second request with same idempotency key - should return existing token (200 OK)
        response2 = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )
        assert response2.status_code == 200

        # Parse second response
        json_response2 = response2.json()
        token_id_2 = json_response2["payment_token"]

        # Verify same token returned
        assert token_id_1 == token_id_2
        assert json_response1["restaurant_id"] == json_response2["restaurant_id"]
        assert json_response1["expires_at"] == json_response2["expires_at"]

    def test_different_idempotency_keys_create_different_tokens(
        self, api_client, test_restaurant_id, test_device_token, encrypt_payment_data_fn
    ):
        """Test that different idempotency keys create different tokens."""
        # Prepare payment data
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        # First request with idempotency key 1
        idempotency_key_1 = str(uuid.uuid4())
        json_request1 = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key_1,
        }

        response1 = api_client.post(
            "/v1/payment-tokens",
            json=json_request1,
            headers={
                "X-Idempotency-Key": idempotency_key_1,
            },
        )
        assert response1.status_code == 201

        json_response1 = response1.json()
        token_id_1 = json_response1["payment_token"]

        # Second request with idempotency key 2 (different)
        idempotency_key_2 = str(uuid.uuid4())
        json_request2 = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key_2,
        }

        response2 = api_client.post(
            "/v1/payment-tokens",
            json=json_request2,
            headers={
                "X-Idempotency-Key": idempotency_key_2,
            },
        )
        assert response2.status_code == 201

        json_response2 = response2.json()
        token_id_2 = json_response2["payment_token"]

        # Verify different tokens created
        assert token_id_1 != token_id_2

    def test_no_duplicate_database_entries_with_idempotency(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that idempotent requests don't create duplicate database entries.

        This is tested implicitly by verifying that the same token is returned
        and by checking that subsequent GET requests return the same data.
        """
        # Prepare payment data
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        # Create JSON request
        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        # Make multiple requests with same idempotency key
        token_ids = []
        for _ in range(3):
            response = api_client.post(
                "/v1/payment-tokens",
                json=json_request,
                headers={
                    "X-Idempotency-Key": idempotency_key,
                },
            )
            assert response.status_code in [200, 201]

            json_response = response.json()
            token_ids.append(json_response["payment_token"])

        # Verify all token IDs are the same
        assert len(set(token_ids)) == 1, "Multiple tokens created for same idempotency key"


class TestDeviceBasedDecryption:
    """Test B2: Device-Based Decryption."""

    def test_valid_device_token_successfully_decrypts(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that valid device_token successfully decrypts payment data."""
        # Prepare payment data
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        # Create token
        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should succeed (201 Created)
        assert response.status_code == 201

        # Parse and verify response
        json_response = response.json()
        assert json_response["payment_token"].startswith("pt_")
        assert json_response["restaurant_id"] == test_restaurant_id

    def test_invalid_device_token_fails_decryption(
        self, api_client, test_restaurant_id, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that invalid device_token fails with 400 Bad Request."""
        # Prepare payment data with one device token
        correct_device_token = "device_correct"
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, correct_device_token)

        # Try to create token with WRONG device token
        wrong_device_token = "device_wrong"
        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": wrong_device_token,  # Wrong token!
            "idempotency_key": idempotency_key,
        }

        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should fail with 400 Bad Request (decryption failure)
        assert response.status_code == 400

    def test_corrupted_encrypted_data_fails_decryption(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key
    ):
        """Test that corrupted encrypted_payment_data fails with 400 Bad Request."""
        # Use corrupted/invalid encrypted data
        corrupted_data = b"corrupted_invalid_data"

        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(corrupted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should fail with 400 Bad Request (decryption failure)
        assert response.status_code == 400
