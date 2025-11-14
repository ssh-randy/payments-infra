"""Integration tests for internal decrypt endpoint.

These tests verify the complete decrypt flow including:
- Service authentication
- Token retrieval from database
- Decryption with service keys
- Audit logging
- Error handling
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

# Add the shared protos to the path
sys.path.insert(0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python")
sys.path.insert(0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python/payments_proto")

from payments_proto.payments.v1 import payment_token_pb2
from payment_token.api.main import app
from payment_token.domain.encryption import encrypt_with_key
from payment_token.domain.services import TokenService
from payment_token.domain.token import PaymentData
from payment_token.infrastructure.database import get_db
from payment_token.infrastructure.models import (
    DecryptAuditLog,
    PaymentToken as PaymentTokenModel,
)


@pytest.fixture
def client(db_session, service_key, monkeypatch):
    """Create a test client with database and KMS dependency overrides."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Override KMS client to use test key (monkeypatch module function)
    def override_get_kms_client():
        mock_kms = Mock()
        mock_kms.get_service_encryption_key.return_value = service_key
        return mock_kms

    # Monkeypatch the get_kms_client function in internal_routes module
    from payment_token.api import internal_routes

    monkeypatch.setattr(internal_routes, "get_kms_client", override_get_kms_client)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_payment_data():
    """Create sample payment data for testing."""
    return PaymentData(
        card_number="4111111111111111",
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="John Doe",
    )


@pytest.fixture
def encrypted_token(db_session, service_key, sample_payment_data, test_restaurant_id):
    """Create an encrypted payment token in the database."""
    # Encrypt the payment data
    payment_data_bytes = sample_payment_data.to_bytes()
    encrypted_data = encrypt_with_key(payment_data_bytes, service_key)

    # Serialize encrypted data (nonce + ciphertext)
    token_service = TokenService()
    encrypted_payment_data = token_service._serialize_encrypted_data(encrypted_data)

    # Create token in database
    token = PaymentTokenModel(
        payment_token="pt_test_123",
        restaurant_id=test_restaurant_id,  # Use UUID format
        encrypted_payment_data=encrypted_payment_data,
        encryption_key_version="v1",
        device_token="device_789",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=24),
        token_metadata={
            "card_brand": "visa",
            "last4": "1111",
            "exp_month": "12",
            "exp_year": "2025",
        },
    )

    db_session.add(token)
    db_session.commit()

    return token


class TestDecryptEndpoint:
    """Test suite for POST /internal/v1/decrypt endpoint."""

    def test_successful_decryption(
        self, client, db_session, encrypted_token, service_key, test_restaurant_id
    ):
        """Test successful token decryption with all validations."""
        # Create protobuf request
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_test_123"
        request.restaurant_id = test_restaurant_id
        request.requesting_service = "auth-processor-worker"

        # Send request
        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": "req_test_001",
                "Content-Type": "application/x-protobuf",
            },
        )

        # Verify response
        assert response.status_code == 200

        # Parse response
        response_proto = payment_token_pb2.DecryptPaymentTokenResponse()
        response_proto.ParseFromString(response.content)

        # Verify payment data
        assert response_proto.payment_data.card_number == "4111111111111111"
        assert response_proto.payment_data.exp_month == "12"
        assert response_proto.payment_data.exp_year == "2025"
        assert response_proto.payment_data.cvv == "123"
        assert response_proto.payment_data.cardholder_name == "John Doe"

        # Verify metadata
        assert response_proto.metadata["card_brand"] == "visa"
        assert response_proto.metadata["last4"] == "1111"

        # Verify audit log entry was created
        audit_entry = (
            db_session.query(DecryptAuditLog)
            .filter(DecryptAuditLog.payment_token == "pt_test_123")
            .first()
        )
        assert audit_entry is not None
        assert audit_entry.success is True
        assert audit_entry.requesting_service == "auth-processor-worker"
        assert audit_entry.request_id == "req_test_001"

    def test_missing_service_auth_header(self, client, test_restaurant_id):
        """Test that request fails without X-Service-Auth header."""
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_test_123"
        request.restaurant_id = test_restaurant_id

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Request-ID": "req_test_002",
            },
        )

        assert response.status_code == 401

    def test_missing_request_id_header(self, client, test_restaurant_id):
        """Test that request fails without X-Request-ID header."""
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_test_123"
        request.restaurant_id = test_restaurant_id

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:auth-processor-worker",
            },
        )

        assert response.status_code == 400

    def test_unauthorized_service(self, client, test_restaurant_id):
        """Test that unauthorized service is rejected."""
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_test_123"
        request.restaurant_id = test_restaurant_id

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:unauthorized-service",
                "X-Request-ID": "req_test_003",
            },
        )

        assert response.status_code == 403

    def test_token_not_found(self, client, db_session, test_restaurant_id):
        """Test that non-existent token returns 404."""
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_nonexistent"
        request.restaurant_id = test_restaurant_id

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": "req_test_004",
            },
        )

        assert response.status_code == 404

        # Verify audit log entry for failure
        audit_entry = (
            db_session.query(DecryptAuditLog)
            .filter(DecryptAuditLog.payment_token == "pt_nonexistent")
            .first()
        )
        assert audit_entry is not None
        assert audit_entry.success is False
        assert audit_entry.error_code == "token_not_found"

    def test_restaurant_mismatch(
        self, client, db_session, encrypted_token
    ):
        """Test that restaurant ID mismatch returns 403."""
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_test_123"
        request.restaurant_id = "87654321-4321-4321-4321-cba987654321"  # Wrong restaurant ID (UUID)

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": "req_test_005",
            },
        )

        assert response.status_code == 403

        # Verify audit log entry for failure
        audit_entry = (
            db_session.query(DecryptAuditLog)
            .filter(DecryptAuditLog.request_id == "req_test_005")
            .first()
        )
        assert audit_entry is not None
        assert audit_entry.success is False
        assert audit_entry.error_code == "restaurant_mismatch"

    def test_expired_token(self, client, db_session, service_key, test_restaurant_id):
        """Test that expired token returns 410."""
        # Create an expired token
        payment_data = PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

        payment_data_bytes = payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, service_key)

        token_service = TokenService()
        encrypted_payment_data = token_service._serialize_encrypted_data(encrypted_data)

        # Create expired token (expires in the past)
        token = PaymentTokenModel(
            payment_token="pt_expired",
            restaurant_id=test_restaurant_id,
            encrypted_payment_data=encrypted_payment_data,
            encryption_key_version="v1",
            device_token="device_789",
            created_at=datetime.utcnow() - timedelta(hours=48),
            expires_at=datetime.utcnow() - timedelta(hours=24),  # Expired 24 hours ago
        )

        db_session.add(token)
        db_session.commit()

        # Try to decrypt expired token
        request = payment_token_pb2.DecryptPaymentTokenRequest()
        request.payment_token = "pt_expired"
        request.restaurant_id = test_restaurant_id

        response = client.post(
            "/internal/v1/decrypt",
            content=request.SerializeToString(),
            headers={
                "X-Service-Auth": "service:auth-processor-worker",
                "X-Request-ID": "req_test_006",
            },
        )

        assert response.status_code == 410

        # Verify audit log entry for failure
        audit_entry = (
            db_session.query(DecryptAuditLog)
            .filter(DecryptAuditLog.request_id == "req_test_006")
            .first()
        )
        assert audit_entry is not None
        assert audit_entry.success is False
        assert audit_entry.error_code == "token_expired"
