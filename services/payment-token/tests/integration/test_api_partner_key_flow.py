"""Integration tests for API Partner Key encryption flow.

These tests verify the complete API partner key flow including:
- TokenService with API partner encrypted data
- Database persistence with encryption_key_id
- End-to-end token creation and retrieval
"""

import base64
import os
from datetime import datetime, timezone

import pytest
from payments_proto.payments.v1 import payment_token_pb2

from payment_token.domain.encryption import (
    EncryptionMetadata,
    encrypt_with_key,
)
from payment_token.domain.services import TokenService
from payment_token.domain.token import PaymentData, TokenMetadata
from payment_token.infrastructure.repository import TokenRepository


class TestAPIPartnerKeyTokenService:
    """Integration tests for TokenService with API partner key flow."""

    @pytest.fixture
    def primary_encryption_key(self, monkeypatch):
        """Provide primary encryption key for tests."""
        key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", key_hex)
        return bytes.fromhex(key_hex)

    @pytest.fixture
    def service_encryption_key(self):
        """Provide service encryption key."""
        return os.urandom(32)

    @pytest.fixture
    def sample_payment_data(self):
        """Create sample payment data for testing."""
        return PaymentData(
            card_number="4532123456789012",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe"
        )

    @pytest.fixture
    def token_service(self):
        """Create TokenService instance."""
        return TokenService()

    def test_create_token_from_api_partner_encrypted_data(
        self,
        token_service,
        primary_encryption_key,
        service_encryption_key,
        sample_payment_data
    ):
        """Test creating token from API partner encrypted data."""
        # Encrypt payment data with primary key (simulating frontend)
        payment_data_bytes = sample_payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

        # Create encryption metadata
        encryption_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        # Create token using API partner key flow
        token = token_service.create_token_from_api_partner_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data=encrypted_data.ciphertext,
            encryption_metadata=encryption_metadata,
            service_encryption_key=service_encryption_key,
            service_key_version="v1",
            metadata_dict={"card_brand": "visa", "last4": "9012"},
            expiration_hours=24
        )

        # Verify token properties
        assert token.payment_token.startswith("pt_")
        assert token.restaurant_id == "550e8400-e29b-41d4-a716-446655440000"
        assert token.encryption_key_id == "primary"  # API partner flow
        assert token.device_token is None  # No device token in API partner flow
        assert token.encryption_key_version == "v1"
        assert token.metadata.card_brand == "visa"
        assert token.metadata.last4 == "9012"

    def test_create_token_extracts_metadata_from_payment_data(
        self,
        token_service,
        primary_encryption_key,
        service_encryption_key,
        sample_payment_data
    ):
        """Test that token creation extracts metadata from decrypted payment data."""
        # Encrypt without providing metadata_dict
        payment_data_bytes = sample_payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

        encryption_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        token = token_service.create_token_from_api_partner_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data=encrypted_data.ciphertext,
            encryption_metadata=encryption_metadata,
            service_encryption_key=service_encryption_key,
            service_key_version="v1",
            metadata_dict=None,  # No metadata provided
            expiration_hours=24
        )

        # Verify extracted metadata
        assert token.metadata.last4 == "9012"
        assert token.metadata.card_brand == "visa"
        assert token.metadata.exp_month == "12"
        assert token.metadata.exp_year == "2025"

    def test_decrypt_token_created_with_api_partner_key(
        self,
        token_service,
        primary_encryption_key,
        service_encryption_key,
        sample_payment_data
    ):
        """Test that token created with API partner key can be decrypted."""
        # Create token
        payment_data_bytes = sample_payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

        encryption_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        token = token_service.create_token_from_api_partner_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data=encrypted_data.ciphertext,
            encryption_metadata=encryption_metadata,
            service_encryption_key=service_encryption_key,
            service_key_version="v1"
        )

        # Decrypt token
        decrypted_payment_data = token_service.decrypt_token(
            token,
            service_encryption_key
        )

        # Verify decrypted data matches original
        assert decrypted_payment_data.card_number == sample_payment_data.card_number
        assert decrypted_payment_data.exp_month == sample_payment_data.exp_month
        assert decrypted_payment_data.exp_year == sample_payment_data.exp_year
        assert decrypted_payment_data.cvv == sample_payment_data.cvv
        assert decrypted_payment_data.cardholder_name == sample_payment_data.cardholder_name


class TestAPIPartnerKeyDatabasePersistence:
    """Integration tests for database persistence with API partner keys."""

    @pytest.fixture
    def primary_encryption_key(self, monkeypatch):
        """Provide primary encryption key for tests."""
        key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", key_hex)
        return bytes.fromhex(key_hex)

    @pytest.fixture
    def token_repository(self, db_session):
        """Create token repository with database session."""
        return TokenRepository(db_session)

    @pytest.fixture
    def token_service(self):
        """Create TokenService instance."""
        return TokenService()

    def test_save_and_retrieve_token_with_encryption_key_id(
        self,
        token_repository,
        token_service,
        primary_encryption_key,
        db_session
    ):
        """Test saving and retrieving token with encryption_key_id."""
        # Create payment data
        payment_data = PaymentData(
            card_number="4111111111111111",
            exp_month="06",
            exp_year="2026",
            cvv="456",
            cardholder_name="Jane Smith"
        )

        # Encrypt with primary key
        service_key = os.urandom(32)
        payment_data_bytes = payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

        encryption_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        # Create token
        token = token_service.create_token_from_api_partner_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data=encrypted_data.ciphertext,
            encryption_metadata=encryption_metadata,
            service_encryption_key=service_key,
            service_key_version="v1"
        )

        # Save to database
        token_repository.save_token(token)
        db_session.commit()

        # Retrieve from database
        retrieved_token = token_repository.get_token(token.payment_token)

        # Verify
        assert retrieved_token is not None
        assert retrieved_token.payment_token == token.payment_token
        assert retrieved_token.encryption_key_id == "primary"
        assert retrieved_token.device_token is None
        assert retrieved_token.restaurant_id == token.restaurant_id

    def test_query_tokens_by_encryption_key_id(
        self,
        token_repository,
        token_service,
        primary_encryption_key,
        db_session
    ):
        """Test that encryption_key_id is properly indexed and queryable."""
        # Create multiple tokens
        service_key = os.urandom(32)

        for i in range(3):
            payment_data = PaymentData(
                card_number=f"411111111111111{i}",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name=f"User {i}"
            )

            payment_data_bytes = payment_data.to_bytes()
            encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

            encryption_metadata = EncryptionMetadata(
                key_id="primary",
                algorithm="AES-256-GCM",
                iv=base64.b64encode(encrypted_data.nonce).decode()
            )

            token = token_service.create_token_from_api_partner_encrypted_data(
                restaurant_id="550e8400-e29b-41d4-a716-446655440000",
                encrypted_payment_data=encrypted_data.ciphertext,
                encryption_metadata=encryption_metadata,
                service_encryption_key=service_key,
                service_key_version="v1"
            )

            token_repository.save_token(token)

        db_session.commit()

        # Query by encryption_key_id using raw SQL (since repository doesn't have this method yet)
        from payment_token.infrastructure.models import PaymentToken as PaymentTokenModel

        tokens_with_primary_key = (
            db_session.query(PaymentTokenModel)
            .filter(PaymentTokenModel.encryption_key_id == "primary")
            .all()
        )

        # Verify we found our tokens
        assert len(tokens_with_primary_key) >= 3
        for db_token in tokens_with_primary_key:
            assert db_token.encryption_key_id == "primary"
            assert db_token.device_token is None


class TestAPIPartnerKeyVsBDKFlow:
    """Tests to verify API partner key flow coexists with BDK flow."""

    @pytest.fixture
    def primary_encryption_key(self, monkeypatch):
        """Provide primary encryption key for tests."""
        key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", key_hex)
        return bytes.fromhex(key_hex)

    @pytest.fixture
    def token_service(self):
        """Create TokenService instance."""
        return TokenService()

    def test_api_partner_token_has_no_device_token(
        self,
        token_service,
        primary_encryption_key
    ):
        """Verify API partner tokens have encryption_key_id but no device_token."""
        payment_data = PaymentData(
            card_number="4532123456789012",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="Test User"
        )

        service_key = os.urandom(32)
        payment_data_bytes = payment_data.to_bytes()
        encrypted_data = encrypt_with_key(payment_data_bytes, primary_encryption_key)

        encryption_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        token = token_service.create_token_from_api_partner_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data=encrypted_data.ciphertext,
            encryption_metadata=encryption_metadata,
            service_encryption_key=service_key,
            service_key_version="v1"
        )

        # API partner flow characteristics
        assert token.encryption_key_id == "primary"
        assert token.device_token is None

    def test_bdk_token_has_device_token_no_encryption_key_id(
        self,
        token_service
    ):
        """Verify BDK tokens have device_token but no encryption_key_id."""
        from payment_token.domain.encryption import (
            EncryptedData,
            derive_device_key,
            encrypt_with_key as encrypt_key
        )

        # Simulate BDK flow
        bdk = os.urandom(32)
        device_token = "device-12345"

        # Derive device key
        device_key = derive_device_key(bdk, device_token)

        # Encrypt payment data
        payment_data = PaymentData(
            card_number="4532123456789012",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="Test User"
        )

        payment_data_bytes = payment_data.to_bytes()
        encrypted_with_device_key = encrypt_key(payment_data_bytes, device_key)

        # Create token using BDK flow
        service_key = os.urandom(32)
        token = token_service.create_token_from_device_encrypted_data(
            restaurant_id="550e8400-e29b-41d4-a716-446655440000",
            encrypted_payment_data_from_device=encrypted_with_device_key,
            device_token=device_token,
            bdk=bdk,
            service_encryption_key=service_key,
            service_key_version="v1"
        )

        # BDK flow characteristics
        assert token.device_token == device_token
        assert token.encryption_key_id is None  # BDK flow doesn't use this
