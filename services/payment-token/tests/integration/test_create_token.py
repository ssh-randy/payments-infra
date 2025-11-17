"""Integration tests for POST /v1/payment-tokens endpoint.

Tests the complete flow of token creation including:
- JSON request/response handling
- Device decryption and re-encryption
- Idempotency
- Database persistence
- Error handling
"""

import base64
import hashlib
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, '/Users/randy/sudocodeai/demos/payments-infra/shared/python/payments_proto')
from payments_proto.payments.v1 import payment_token_pb2

from payment_token.api.main import app
from payment_token.domain.encryption import encrypt_with_key, derive_device_key
from payment_token.domain.token import PaymentData
from payment_token.infrastructure.database import Base
from payment_token.infrastructure.models import PaymentToken as PaymentTokenModel


# Test database setup
# Use file URI with shared cache so all connections see the same database
TEST_DATABASE_URL = "sqlite:///file:test_db?mode=memory&cache=shared&uri=true"


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine and run Alembic migrations once for all tests."""
    # Import models to ensure they're registered
    from payment_token.infrastructure import models  # noqa: F401

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=None,  # Disable pooling for testing
    )

    # Run Alembic migrations programmatically with our test connection
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # Use a connection instead of letting Alembic create its own
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

    yield engine

    # Downgrade to base (clean up all tables)
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "base")

    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create a session factory for the test database."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def test_db(test_engine, test_session_factory):
    """Provide a clean database for each test by truncating tables."""
    # Clean up data between tests (truncate all tables)
    with test_engine.connect() as connection:
        # Disable foreign key constraints for SQLite
        connection.execute(text("PRAGMA foreign_keys = OFF"))

        # Truncate all tables
        connection.execute(text("DELETE FROM decrypt_audit_log"))
        connection.execute(text("DELETE FROM token_idempotency_keys"))
        connection.execute(text("DELETE FROM payment_tokens"))
        connection.execute(text("DELETE FROM encryption_keys"))

        # Re-enable foreign key constraints
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.commit()

    yield test_session_factory, test_engine


@pytest.fixture(scope="function")
def client(test_db, monkeypatch):
    """Create test client with test database."""
    TestingSessionLocal, engine = test_db

    # Override settings with test configuration
    from payment_token import config
    monkeypatch.setattr(config.settings, "bdk_kms_key_id", "test-kms-key-id")
    monkeypatch.setattr(config.settings, "current_key_version", "v1")

    # Override database dependency
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Override KMS client to use test key
    def override_get_kms_client():
        from unittest.mock import Mock
        mock_kms = Mock()
        # Return deterministic test BDK
        mock_kms.get_bdk.return_value = hashlib.sha256(b"test-bdk").digest()
        return mock_kms

    # Override service encryption key
    def override_get_service_key():
        return hashlib.sha256(b"test-service-key").digest()

    # Use FastAPI's dependency override
    from payment_token.api import dependencies
    app.dependency_overrides[dependencies.get_db] = override_get_db
    app.dependency_overrides[dependencies.get_kms_client] = override_get_kms_client
    app.dependency_overrides[dependencies.get_service_encryption_key] = override_get_service_key

    yield TestClient(app)

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_bdk():
    """Test Base Derivation Key."""
    return hashlib.sha256(b"test-bdk").digest()


@pytest.fixture
def device_token():
    """Test device token."""
    return "device-123456"


@pytest.fixture
def restaurant_id():
    """Test restaurant ID."""
    return str(uuid.uuid4())


@pytest.fixture
def payment_data():
    """Test payment data."""
    return PaymentData(
        card_number="4111111111111111",
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="John Doe",
    )


@pytest.fixture
def device_encrypted_payment_data(payment_data, test_bdk, device_token):
    """Create device-encrypted payment data for testing.

    Simulates what the POS device would send.
    """
    # Derive device key from BDK + device_token
    device_key = derive_device_key(test_bdk, device_token)

    # Encrypt payment data with device key
    payment_data_bytes = payment_data.to_bytes()
    encrypted_data = encrypt_with_key(payment_data_bytes, device_key)

    # Serialize (nonce + ciphertext)
    return encrypted_data.nonce + encrypted_data.ciphertext


def test_create_token_success(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test successful token creation."""
    idempotency_key = str(uuid.uuid4())

    # Prepare JSON request
    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
        "idempotency_key": idempotency_key,
        "metadata": {
            "pos_terminal": "T123",
            "transaction_type": "sale",
        },
    }

    # Send request
    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
            "X-Idempotency-Key": idempotency_key,
        },
    )

    # Assert response
    assert response.status_code == 201
    assert response.headers["content-type"] == "application/json"

    # Parse JSON response
    json_response = response.json()

    # Verify response fields
    assert json_response["payment_token"].startswith("pt_")
    assert json_response["restaurant_id"] == restaurant_id
    assert json_response["expires_at"] > int(datetime.utcnow().timestamp())
    assert "card_brand" in json_response["metadata"]
    assert "last4" in json_response["metadata"]
    assert json_response["metadata"]["last4"] == "1111"


def test_create_token_idempotency(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test idempotency: same idempotency key returns same token."""
    idempotency_key = str(uuid.uuid4())

    # Prepare JSON request
    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
        "idempotency_key": idempotency_key,
    }

    # First request
    response1 = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
            "X-Idempotency-Key": idempotency_key,
        },
    )

    assert response1.status_code == 201

    json_response1 = response1.json()
    token1 = json_response1["payment_token"]

    # Second request with same idempotency key
    response2 = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
            "X-Idempotency-Key": idempotency_key,
        },
    )

    # Should return 200 OK (idempotent) with same token
    assert response2.status_code == 200

    json_response2 = response2.json()
    token2 = json_response2["payment_token"]

    # Verify same token returned
    assert token1 == token2


def test_create_token_missing_restaurant_id(client, device_token, device_encrypted_payment_data):
    """Test validation: missing restaurant_id."""
    json_request = {
        "restaurant_id": "",  # Empty
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
    }

    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
        },
    )

    assert response.status_code == 400
    assert "restaurant_id" in response.json()["detail"]


def test_create_token_missing_encrypted_data(client, restaurant_id, device_token):
    """Test validation: missing encrypted_payment_data."""
    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": "",  # Empty
        "device_token": device_token,
    }

    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
        },
    )

    assert response.status_code == 400
    assert "encrypted_payment_data" in response.json()["detail"]


def test_create_token_invalid_device_token(client, restaurant_id):
    """Test decryption failure: invalid device_token."""
    # Use garbage encrypted data that won't decrypt
    invalid_encrypted_data = b"invalid_encrypted_data_that_wont_decrypt"

    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(invalid_encrypted_data).decode(),
        "device_token": "wrong-device-token",
    }

    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
        },
    )

    # Should fail with 400 due to decryption failure
    assert response.status_code == 400
    assert "decrypt" in response.json()["detail"].lower()


def test_create_token_unauthorized(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test authentication: missing or invalid API key."""
    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
    }

    # Request without Authorization header
    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
    )

    assert response.status_code == 401


def test_create_token_invalid_api_key(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test authentication: API key too short."""
    json_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
    }

    # Request with invalid API key (too short)
    response = client.post(
        "/v1/payment-tokens",
        json=json_request,
        headers={
            "Authorization": "Bearer short",
        },
    )

    assert response.status_code == 401


def test_get_token_success(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test GET /v1/payment-tokens/{token_id} success."""
    # First create a token
    json_create_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
    }

    create_response = client.post(
        "/v1/payment-tokens",
        json=json_create_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
        },
    )

    assert create_response.status_code == 201

    json_create_response = create_response.json()
    token_id = json_create_response["payment_token"]

    # Now retrieve it
    get_response = client.get(
        f"/v1/payment-tokens/{token_id}",
        params={"restaurant_id": restaurant_id},
        headers={"Authorization": "Bearer test-api-key-1234567890"},
    )

    assert get_response.status_code == 200

    json_get_response = get_response.json()

    assert json_get_response["payment_token"] == token_id
    assert json_get_response["restaurant_id"] == restaurant_id
    assert json_get_response["expires_at"] > int(datetime.utcnow().timestamp())
    assert "card_brand" in json_get_response["metadata"]


def test_get_token_not_found(client, restaurant_id):
    """Test GET token with non-existent token ID."""
    response = client.get(
        "/v1/payment-tokens/pt_nonexistent",
        params={"restaurant_id": restaurant_id},
        headers={"Authorization": "Bearer test-api-key-1234567890"},
    )

    assert response.status_code == 404


def test_get_token_wrong_restaurant(client, restaurant_id, device_token, device_encrypted_payment_data):
    """Test GET token with wrong restaurant ID (ownership check)."""
    # Create token for one restaurant
    json_create_request = {
        "restaurant_id": restaurant_id,
        "encrypted_payment_data": base64.b64encode(device_encrypted_payment_data).decode(),
        "device_token": device_token,
    }

    create_response = client.post(
        "/v1/payment-tokens",
        json=json_create_request,
        headers={
            "Authorization": "Bearer test-api-key-1234567890",
        },
    )

    json_create_response = create_response.json()
    token_id = json_create_response["payment_token"]

    # Try to retrieve with different restaurant ID
    different_restaurant_id = str(uuid.uuid4())
    get_response = client.get(
        f"/v1/payment-tokens/{token_id}",
        params={"restaurant_id": different_restaurant_id},
        headers={"Authorization": "Bearer test-api-key-1234567890"},
    )

    # Should return 404 (not found for this restaurant)
    assert get_response.status_code == 404


def test_get_token_expired(client, test_db, restaurant_id, device_token, device_encrypted_payment_data):
    """Test GET token returns 410 Gone for expired token."""
    # Create token directly in database with expired timestamp
    from payment_token.domain.token import PaymentToken, TokenMetadata
    from payment_token.domain.encryption import encrypt_with_key
    import hashlib

    TestingSessionLocal, _ = test_db
    session = TestingSessionLocal()

    try:
        # Create an expired token
        token_id = f"pt_{uuid.uuid4()}"
        service_key = hashlib.sha256(b"test-service-key").digest()

        # Encrypt some dummy payment data
        encrypted_data = encrypt_with_key(b"dummy_payment_data", service_key)
        encrypted_bytes = encrypted_data.nonce + encrypted_data.ciphertext

        # Create token that expired 1 hour ago
        expired_token = PaymentToken(
            payment_token=token_id,
            restaurant_id=restaurant_id,
            encrypted_payment_data=encrypted_bytes,
            encryption_key_version="v1",
            device_token=device_token,
            created_at=datetime.utcnow() - timedelta(hours=25),
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
            metadata=TokenMetadata(
                card_brand="visa",
                last4="1111",
                exp_month="12",
                exp_year="2025",
            ),
        )

        # Save directly to database
        token_model = PaymentTokenModel(
            payment_token=expired_token.payment_token,
            restaurant_id=expired_token.restaurant_id,
            encrypted_payment_data=expired_token.encrypted_payment_data,
            encryption_key_version=expired_token.encryption_key_version,
            device_token=expired_token.device_token,
            created_at=expired_token.created_at,
            expires_at=expired_token.expires_at,
            token_metadata=expired_token.metadata.to_dict() if expired_token.metadata else None,
        )
        session.add(token_model)
        session.commit()

        # Try to retrieve expired token
        get_response = client.get(
            f"/v1/payment-tokens/{token_id}",
            params={"restaurant_id": restaurant_id},
            headers={"Authorization": "Bearer test-api-key-1234567890"},
        )

        # Should return 410 Gone
        assert get_response.status_code == 410
        assert "expired" in get_response.json()["detail"].lower()

    finally:
        session.close()
