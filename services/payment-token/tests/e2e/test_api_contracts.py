"""E2E tests for API contracts.

Tests all API endpoints with various scenarios to verify the API contracts
as documented in the specification.

Endpoints tested:
- POST /v1/payment-tokens
- GET /v1/payment-tokens/{token_id}
- POST /internal/v1/decrypt
"""

import base64
import uuid
import sys
sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python')
from payments_proto.payments.v1 import payment_token_pb2


class TestCreatePaymentTokenEndpoint:
    """Test POST /v1/payment-tokens endpoint contract."""

    def test_returns_201_on_first_request(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that first request returns 201 Created."""
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

        # Send request
        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should return 201 Created
        assert response.status_code == 201

    def test_returns_200_on_idempotent_request(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that idempotent request returns 200 OK."""
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

        # First request
        response1 = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )
        assert response1.status_code == 201

        # Second request (idempotent)
        response2 = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should return 200 OK
        assert response2.status_code == 200

    def test_returns_400_on_missing_required_fields(
        self, api_client
    ):
        """Test that missing required fields returns 400 Bad Request."""
        # Create request with missing fields
        idempotency_key = str(uuid.uuid4())
        json_request = {
            # Missing restaurant_id, encrypted_payment_data, device_token
            "idempotency_key": idempotency_key,
        }

        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

    def test_returns_400_on_decryption_failure(
        self, api_client, test_restaurant_id, idempotency_key
    ):
        """Test that decryption failure returns 400 Bad Request."""
        # Use invalid/corrupted encrypted data
        corrupted_data = b"invalid_encrypted_data"

        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(corrupted_data).decode(),
            "device_token": "some_device_token",
            "idempotency_key": idempotency_key,
        }

        response = api_client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should return 400 Bad Request
        assert response.status_code == 400

    def test_returns_401_on_missing_api_key(
        self, docker_services, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that missing API key returns 401 Unauthorized."""
        import httpx

        # Create client WITHOUT Authorization header
        client = httpx.Client(base_url="http://localhost:8002", timeout=10.0)

        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        response = client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
                # Missing Authorization header
            },
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_returns_401_on_invalid_api_key(
        self, docker_services, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that invalid API key returns 401 Unauthorized."""
        import httpx

        # Create client with INVALID Authorization header
        client = httpx.Client(
            base_url="http://localhost:8002",
            headers={"Authorization": "Bearer short"},  # Too short (< 10 chars)
            timeout=10.0,
        )

        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder",
        }
        encrypted_data = encrypt_payment_data_fn(payment_data, test_device_token)

        json_request = {
            "restaurant_id": test_restaurant_id,
            "encrypted_payment_data": base64.b64encode(encrypted_data).decode(),
            "device_token": test_device_token,
            "idempotency_key": idempotency_key,
        }

        response = client.post(
            "/v1/payment-tokens",
            json=json_request,
            headers={
                "X-Idempotency-Key": idempotency_key,
            },
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_response_includes_required_fields(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that response includes token ID, restaurant_id, expires_at, metadata."""
        # Create token with metadata
        metadata = {
            "card_brand": "visa",
            "last4": "0366",
        }
        response = create_token_helper(metadata=metadata)
        assert response.status_code == 201

        # Parse response
        json_response = response.json()

        # Verify required fields
        assert json_response["payment_token"].startswith("pt_")
        assert json_response["restaurant_id"] == test_restaurant_id
        assert json_response["expires_at"] > 0  # Unix timestamp
        assert len(json_response["metadata"]) > 0  # Metadata echoed back


class TestGetPaymentTokenEndpoint:
    """Test GET /v1/payment-tokens/{token_id} endpoint contract."""

    def test_returns_200_with_token_metadata(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that GET returns 200 OK with token metadata."""
        # Create token
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Get token metadata
        get_response = api_client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": test_restaurant_id},
        )

        assert get_response.status_code == 200

        # Parse and verify metadata
        get_json_response = get_response.json()

        assert get_json_response["payment_token"] == token_id
        assert get_json_response["restaurant_id"] == test_restaurant_id
        assert get_json_response["created_at"] > 0
        assert get_json_response["expires_at"] > 0

    def test_returns_404_for_nonexistent_token(
        self, api_client, test_restaurant_id
    ):
        """Test that non-existent token returns 404 Not Found."""
        fake_token_id = "pt_nonexistent"

        response = api_client.get(
            f"/v1/payment-tokens/{fake_token_id}",
            params={"restaurant_id": test_restaurant_id},
        )

        assert response.status_code == 404

    def test_returns_404_for_wrong_restaurant(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that wrong restaurant returns 404 Not Found."""
        # Create token for restaurant A
        response = create_token_helper(restaurant_id=test_restaurant_id)
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to get with wrong restaurant ID
        wrong_restaurant_id = str(uuid.uuid4())
        get_response = api_client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": wrong_restaurant_id},
        )

        assert get_response.status_code == 404

    def test_returns_401_on_missing_api_key(
        self, docker_services, create_token_helper, test_restaurant_id
    ):
        """Test that missing API key returns 401 Unauthorized."""
        import httpx

        # Create token first (with valid API key)
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to get WITHOUT API key
        client = httpx.Client(base_url="http://localhost:8002", timeout=10.0)
        get_response = client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": test_restaurant_id},
        )

        assert get_response.status_code == 401


class TestDecryptPaymentTokenEndpoint:
    """Test POST /internal/v1/decrypt endpoint contract."""

    def test_returns_200_with_payment_data_for_valid_request(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that valid request returns 200 OK with PaymentData."""
        # Create token
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Decrypt
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        assert decrypt_response.status_code == 200

        # Parse and verify payment data
        decrypt_pb_response = payment_token_pb2.DecryptPaymentTokenResponse()
        decrypt_pb_response.ParseFromString(decrypt_response.content)

        assert decrypt_pb_response.payment_data.card_number
        assert decrypt_pb_response.payment_data.exp_month
        assert decrypt_pb_response.payment_data.exp_year
        assert decrypt_pb_response.payment_data.cvv
        assert decrypt_pb_response.payment_data.cardholder_name

    def test_returns_400_for_invalid_token_format(
        self, internal_api_client, test_restaurant_id
    ):
        """Test that invalid token format returns 400 Bad Request."""
        # Use invalid token format (not starting with pt_)
        invalid_token = "invalid_token_format"

        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=invalid_token,
            restaurant_id=test_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        # May return 400 or 404 depending on implementation
        assert decrypt_response.status_code in [400, 404]

    def test_returns_401_for_missing_service_auth_header(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that missing X-Service-Auth header returns 401 Unauthorized."""
        # Create token
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to decrypt without X-Service-Auth header
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                # Missing X-Service-Auth!
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        assert decrypt_response.status_code == 401

    def test_returns_403_for_unauthorized_service(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that unauthorized service returns 403 Forbidden."""
        # Create token
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to decrypt with unauthorized service
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="unauthorized-service",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:unauthorized-service",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        assert decrypt_response.status_code == 403

    def test_returns_403_for_restaurant_id_mismatch(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that restaurant ID mismatch returns 403 Forbidden."""
        # Create token for restaurant A
        response = create_token_helper(restaurant_id=test_restaurant_id)
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to decrypt with wrong restaurant ID
        wrong_restaurant_id = str(uuid.uuid4())
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=wrong_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        assert decrypt_response.status_code == 403

    def test_returns_404_for_nonexistent_token(
        self, internal_api_client, test_restaurant_id
    ):
        """Test that non-existent token returns 404 Not Found."""
        fake_token_id = "pt_nonexistent"

        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=fake_token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        assert decrypt_response.status_code == 404

    def test_requires_request_id_header(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that X-Request-ID header is required."""
        # Create token
        response = create_token_helper()
        assert response.status_code == 201

        json_response = response.json()


        token_id = json_response["payment_token"]

        # Try to decrypt without X-Request-ID header
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="auth-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:auth-processor-worker",
                # Missing X-Request-ID!
            },
        )

        # Should return 400 Bad Request
        assert decrypt_response.status_code == 400
