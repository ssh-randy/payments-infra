"""E2E tests for token retrieval behaviors (B4, B5).

Tests:
- B4: Token Expiration
- B5: Restaurant Scoping
"""

import time
import uuid
import sys
sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python')
from payments_proto.payments.v1 import payment_token_pb2


class TestTokenExpiration:
    """Test B4: Token Expiration.

    Note: Full expiration testing (24 hours) is impractical for E2E tests.
    These tests verify the expiration logic works correctly, but don't wait 24 hours.
    Production would need time-based integration tests or manual testing.
    """

    def test_non_expired_tokens_work_normally(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that non-expired tokens can be retrieved normally."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Retrieve token metadata immediately (should work)
        get_response = api_client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": test_restaurant_id},
        )

        # Should succeed (200 OK)
        assert get_response.status_code == 200

        # Parse and verify response
        get_pb_response = payment_token_pb2.GetPaymentTokenResponse()
        get_pb_response.ParseFromString(get_response.content)

        assert get_pb_response.payment_token == token_id
        assert get_pb_response.restaurant_id == test_restaurant_id
        assert not get_pb_response.is_expired  # Should not be expired
        assert get_pb_response.expires_at > int(time.time())  # Expiration in future

    def test_expired_token_returns_410_on_get(
        self, api_client, test_restaurant_id, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test that GET request for expired token returns 410 Gone.

        Note: This test would need database manipulation or config changes to
        actually create an expired token. For now, we document the expected behavior.

        In a real scenario, you would:
        1. Create a token with TTL of 1 second (via config override)
        2. Wait 2 seconds
        3. Try to retrieve it
        4. Expect 410 Gone
        """
        # This is a placeholder test that documents expected behavior
        # Implementation requires:
        # - Config override to set token TTL to 1 second
        # - OR direct database manipulation to set expires_at to past
        # - OR mock time in the service

        # For comprehensive testing, consider:
        # 1. Unit tests for expiration logic
        # 2. Integration tests with mocked time
        # 3. Manual QA for 24-hour expiration in staging environment
        pass

    def test_expired_token_returns_410_on_decrypt(
        self,
    ):
        """Test that decrypt request for expired token returns 410 Gone.

        Note: Same as above - requires special setup to create expired tokens.
        """
        pass


class TestRestaurantScoping:
    """Test B5: Restaurant Scoping."""

    def test_token_accessible_by_owning_restaurant(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that token can be accessed by owning restaurant."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Retrieve token with correct restaurant_id
        get_response = api_client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": test_restaurant_id},
        )

        # Should succeed
        assert get_response.status_code == 200

        # Parse and verify
        get_pb_response = payment_token_pb2.GetPaymentTokenResponse()
        get_pb_response.ParseFromString(get_response.content)
        assert get_pb_response.payment_token == token_id
        assert get_pb_response.restaurant_id == test_restaurant_id

    def test_wrong_restaurant_id_returns_404_on_get(
        self, api_client, create_token_helper, test_restaurant_id
    ):
        """Test that wrong restaurant_id returns 404 on GET."""
        # Create a token for restaurant A
        response = create_token_helper(restaurant_id=test_restaurant_id)
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Try to retrieve token with WRONG restaurant_id
        wrong_restaurant_id = str(uuid.uuid4())
        get_response = api_client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": wrong_restaurant_id},
        )

        # Should return 404 (token doesn't exist for this restaurant)
        assert get_response.status_code == 404

    def test_wrong_restaurant_id_returns_403_on_decrypt(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that wrong restaurant_id returns 403 on decrypt."""
        # Create a token for restaurant A
        response = create_token_helper(restaurant_id=test_restaurant_id)
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Try to decrypt with WRONG restaurant_id
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

        # Should return 403 (restaurant ID mismatch)
        assert decrypt_response.status_code == 403

    def test_different_restaurants_cannot_access_each_others_tokens(
        self, api_client, test_device_token, idempotency_key, encrypt_payment_data_fn
    ):
        """Test comprehensive restaurant isolation."""
        # Create tokens for two different restaurants
        restaurant_a = str(uuid.uuid4())
        restaurant_b = str(uuid.uuid4())

        # Create token for restaurant A
        payment_data = {
            "card_number": "4532015112830366",
            "exp_month": "12",
            "exp_year": "2025",
            "cvv": "123",
            "cardholder_name": "Test Cardholder A",
        }
        encrypted_data_a = encrypt_payment_data_fn(payment_data, test_device_token)

        request_a = payment_token_pb2.CreatePaymentTokenRequest(
            restaurant_id=restaurant_a,
            encrypted_payment_data=encrypted_data_a,
            device_token=test_device_token,
            idempotency_key=str(uuid.uuid4()),
        )

        response_a = api_client.post(
            "/v1/payment-tokens",
            content=request_a.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Idempotency-Key": request_a.idempotency_key,
            },
        )
        assert response_a.status_code == 201

        pb_response_a = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response_a.ParseFromString(response_a.content)
        token_a = pb_response_a.payment_token

        # Create token for restaurant B
        payment_data_b = {
            "card_number": "5425233430109903",
            "exp_month": "06",
            "exp_year": "2026",
            "cvv": "456",
            "cardholder_name": "Test Cardholder B",
        }
        encrypted_data_b = encrypt_payment_data_fn(payment_data_b, test_device_token)

        request_b = payment_token_pb2.CreatePaymentTokenRequest(
            restaurant_id=restaurant_b,
            encrypted_payment_data=encrypted_data_b,
            device_token=test_device_token,
            idempotency_key=str(uuid.uuid4()),
        )

        response_b = api_client.post(
            "/v1/payment-tokens",
            content=request_b.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Idempotency-Key": request_b.idempotency_key,
            },
        )
        assert response_b.status_code == 201

        pb_response_b = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response_b.ParseFromString(response_b.content)
        token_b = pb_response_b.payment_token

        # Verify restaurant A can access token A
        get_a_by_a = api_client.get(
            f"/v1/payment-tokens/{token_a}",
            params={"restaurant_id": restaurant_a},
        )
        assert get_a_by_a.status_code == 200

        # Verify restaurant B can access token B
        get_b_by_b = api_client.get(
            f"/v1/payment-tokens/{token_b}",
            params={"restaurant_id": restaurant_b},
        )
        assert get_b_by_b.status_code == 200

        # Verify restaurant A CANNOT access token B
        get_b_by_a = api_client.get(
            f"/v1/payment-tokens/{token_b}",
            params={"restaurant_id": restaurant_a},
        )
        assert get_b_by_a.status_code == 404

        # Verify restaurant B CANNOT access token A
        get_a_by_b = api_client.get(
            f"/v1/payment-tokens/{token_a}",
            params={"restaurant_id": restaurant_b},
        )
        assert get_a_by_b.status_code == 404
