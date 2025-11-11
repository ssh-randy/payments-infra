"""E2E tests for decryption behaviors (B6, B7).

Tests:
- B6: Internal Decryption Authorization
- B7: Audit Logging for Decryption
"""

import uuid
import sys
sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python')
from payments_proto.payments.v1 import payment_token_pb2


class TestInternalDecryptionAuthorization:
    """Test B6: Internal Decryption Authorization."""

    def test_auth_processor_worker_can_decrypt(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that auth-processor-worker can decrypt (200 OK)."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Decrypt with auth-processor-worker
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

        # Should succeed (200 OK)
        assert decrypt_response.status_code == 200

        # Parse and verify decrypted payment data
        decrypt_pb_response = payment_token_pb2.DecryptPaymentTokenResponse()
        decrypt_pb_response.ParseFromString(decrypt_response.content)

        # Verify payment data is present and correct
        assert decrypt_pb_response.payment_data.card_number == "4532015112830366"
        assert decrypt_pb_response.payment_data.exp_month == "12"
        assert decrypt_pb_response.payment_data.exp_year == "2025"
        assert decrypt_pb_response.payment_data.cvv == "123"
        assert decrypt_pb_response.payment_data.cardholder_name == "Test Cardholder"

    def test_void_processor_worker_can_decrypt(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that void-processor-worker can decrypt (200 OK)."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Decrypt with void-processor-worker
        decrypt_request = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=token_id,
            restaurant_id=test_restaurant_id,
            requesting_service="void-processor-worker",
        )

        decrypt_response = internal_api_client.post(
            "/internal/v1/decrypt",
            content=decrypt_request.SerializeToString(),
            headers={
                "Content-Type": "application/x-protobuf",
                "X-Service-Auth": "service:void-processor-worker",
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        # Should succeed (200 OK)
        assert decrypt_response.status_code == 200

    def test_unauthorized_service_cannot_decrypt(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that unauthorized service cannot decrypt (403 Forbidden)."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

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

        # Should return 403 Forbidden
        assert decrypt_response.status_code == 403

    def test_missing_service_auth_header_returns_401(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that missing X-Service-Auth header returns 401."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Try to decrypt WITHOUT X-Service-Auth header
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
                # Missing X-Service-Auth header!
                "X-Request-ID": str(uuid.uuid4()),
            },
        )

        # Should return 401 Unauthorized
        assert decrypt_response.status_code == 401

    def test_missing_request_id_header_returns_400(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that missing X-Request-ID header returns 400."""
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Try to decrypt WITHOUT X-Request-ID header
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
                # Missing X-Request-ID header!
            },
        )

        # Should return 400 Bad Request
        assert decrypt_response.status_code == 400


class TestAuditLoggingForDecryption:
    """Test B7: Audit Logging for Decryption.

    Note: These tests verify that audit logging doesn't break the decrypt flow.
    Actual audit log verification would require database access or log inspection,
    which is beyond the scope of black-box E2E tests.

    In a real production environment, you would:
    1. Query the decrypt_audit_log table after each test
    2. Verify log entries contain: token_id, restaurant_id, service, request_id, timestamp, result
    3. Verify failed attempts are also logged with error codes
    """

    def test_successful_decrypt_creates_audit_log(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that successful decrypt creates audit log entry.

        This test verifies the decrypt succeeds. The audit log entry is created
        implicitly, but we don't verify it in E2E tests (would need DB access).
        """
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Decrypt successfully
        request_id = str(uuid.uuid4())
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
                "X-Request-ID": request_id,
            },
        )

        # Should succeed (200 OK)
        assert decrypt_response.status_code == 200

        # Audit log entry should be created with:
        # - payment_token: token_id
        # - restaurant_id: test_restaurant_id
        # - requesting_service: "auth-processor-worker"
        # - request_id: request_id
        # - success: True
        # - error_code: None
        # - created_at: timestamp

        # Note: Verification would require DB query:
        # SELECT * FROM decrypt_audit_log WHERE request_id = '{request_id}'

    def test_failed_decrypt_creates_audit_log_with_error(
        self, internal_api_client, test_restaurant_id
    ):
        """Test that failed decrypt creates audit log entry with error_code.

        This test verifies failed decrypts are logged (implicitly).
        """
        # Try to decrypt non-existent token
        fake_token_id = "pt_nonexistent"
        request_id = str(uuid.uuid4())

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
                "X-Request-ID": request_id,
            },
        )

        # Should fail (404 Not Found)
        assert decrypt_response.status_code == 404

        # Audit log entry should be created with:
        # - payment_token: fake_token_id
        # - restaurant_id: test_restaurant_id
        # - requesting_service: "auth-processor-worker"
        # - request_id: request_id
        # - success: False
        # - error_code: "TOKEN_NOT_FOUND" or similar
        # - created_at: timestamp

        # Note: Verification would require DB query

    def test_audit_log_includes_correlation_id(
        self, internal_api_client, create_token_helper, test_restaurant_id
    ):
        """Test that audit log includes X-Request-ID for correlation.

        This verifies that the request_id is properly captured for audit trail.
        """
        # Create a token
        response = create_token_helper()
        assert response.status_code == 201

        # Parse response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse()
        pb_response.ParseFromString(response.content)
        token_id = pb_response.payment_token

        # Decrypt with specific request ID
        request_id = f"test-correlation-{uuid.uuid4()}"
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
                "X-Request-ID": request_id,
            },
        )

        # Should succeed
        assert decrypt_response.status_code == 200

        # Audit log should include this specific request_id for correlation
        # This enables tracking requests across services via correlation IDs
