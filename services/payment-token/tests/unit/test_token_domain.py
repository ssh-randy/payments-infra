"""Unit tests for token domain models and services."""

import os
from datetime import datetime, timedelta

import pytest

from payment_token.domain.encryption import EncryptedData, encrypt_with_key
from payment_token.domain.services import TokenService, validate_token_for_use
from payment_token.domain.token import (
    PaymentData,
    PaymentToken,
    TokenError,
    TokenExpiredError,
    TokenMetadata,
    TokenOwnershipError,
    _detect_card_brand,
)


class TestPaymentData:
    """Tests for PaymentData domain model."""

    def test_valid_payment_data(self):
        """Test creating valid payment data."""
        data = PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

        assert data.card_number == "4111111111111111"
        assert data.exp_month == "12"
        assert data.exp_year == "2025"
        assert data.cvv == "123"
        assert data.cardholder_name == "John Doe"

    def test_card_number_validation(self):
        """Test card number validation."""
        # Too short
        with pytest.raises(ValueError, match="13-19 digits"):
            PaymentData(
                card_number="411111",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name="John Doe",
            )

        # Too long
        with pytest.raises(ValueError, match="13-19 digits"):
            PaymentData(
                card_number="41111111111111111111",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name="John Doe",
            )

        # Non-numeric
        with pytest.raises(ValueError, match="must be numeric"):
            PaymentData(
                card_number="4111-1111-1111-1111",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name="John Doe",
            )

    def test_exp_month_validation(self):
        """Test expiration month validation."""
        # Invalid month
        with pytest.raises(ValueError, match="between 01 and 12"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="13",
                exp_year="2025",
                cvv="123",
                cardholder_name="John Doe",
            )

        # Wrong format
        with pytest.raises(ValueError, match="2-digit numeric"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="1",
                exp_year="2025",
                cvv="123",
                cardholder_name="John Doe",
            )

    def test_exp_year_validation(self):
        """Test expiration year validation."""
        # Wrong format
        with pytest.raises(ValueError, match="4-digit numeric"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="12",
                exp_year="25",
                cvv="123",
                cardholder_name="John Doe",
            )

    def test_cvv_validation(self):
        """Test CVV validation."""
        # Too short
        with pytest.raises(ValueError, match="3 or 4 digits"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="12",
                exp_year="2025",
                cvv="12",
                cardholder_name="John Doe",
            )

        # Too long
        with pytest.raises(ValueError, match="3 or 4 digits"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="12",
                exp_year="2025",
                cvv="12345",
                cardholder_name="John Doe",
            )

        # 4-digit CVV should work (AMEX)
        data = PaymentData(
            card_number="371111111111114",
            exp_month="12",
            exp_year="2025",
            cvv="1234",
            cardholder_name="John Doe",
        )
        assert data.cvv == "1234"

    def test_cardholder_name_validation(self):
        """Test cardholder name validation."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PaymentData(
                card_number="4111111111111111",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name="",
            )

    def test_serialization_round_trip(self):
        """Test serialization and deserialization."""
        original = PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

        # Serialize
        serialized = original.to_bytes()
        assert isinstance(serialized, bytes)

        # Deserialize
        deserialized = PaymentData.from_bytes(serialized)

        # Should be equal
        assert deserialized.card_number == original.card_number
        assert deserialized.exp_month == original.exp_month
        assert deserialized.exp_year == original.exp_year
        assert deserialized.cvv == original.cvv
        assert deserialized.cardholder_name == original.cardholder_name

    def test_immutability(self):
        """Test that PaymentData is immutable."""
        data = PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

        with pytest.raises(Exception):  # FrozenInstanceError in dataclasses
            data.card_number = "5111111111111111"


class TestTokenMetadata:
    """Tests for TokenMetadata domain model."""

    def test_metadata_creation(self):
        """Test creating metadata."""
        metadata = TokenMetadata(
            card_brand="visa", last4="1111", exp_month="12", exp_year="2025"
        )

        assert metadata.card_brand == "visa"
        assert metadata.last4 == "1111"
        assert metadata.exp_month == "12"
        assert metadata.exp_year == "2025"

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = TokenMetadata(
            card_brand="visa", last4="1111", exp_month="12", exp_year="2025"
        )

        result = metadata.to_dict()
        assert result == {
            "card_brand": "visa",
            "last4": "1111",
            "exp_month": "12",
            "exp_year": "2025",
        }

    def test_metadata_from_dict(self):
        """Test creating metadata from dictionary."""
        data = {
            "card_brand": "mastercard",
            "last4": "5454",
            "exp_month": "06",
            "exp_year": "2026",
        }

        metadata = TokenMetadata.from_dict(data)
        assert metadata.card_brand == "mastercard"
        assert metadata.last4 == "5454"
        assert metadata.exp_month == "06"
        assert metadata.exp_year == "2026"

    def test_metadata_from_dict_none(self):
        """Test creating metadata from None."""
        metadata = TokenMetadata.from_dict(None)
        assert metadata.card_brand is None
        assert metadata.last4 is None

    def test_metadata_from_payment_data(self):
        """Test extracting metadata from payment data."""
        payment_data = PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

        metadata = TokenMetadata.from_payment_data(payment_data)
        assert metadata.card_brand == "visa"
        assert metadata.last4 == "1111"
        assert metadata.exp_month == "12"
        assert metadata.exp_year == "2025"


class TestCardBrandDetection:
    """Tests for card brand detection."""

    def test_visa_detection(self):
        """Test Visa card detection."""
        assert _detect_card_brand("4111111111111111") == "visa"
        assert _detect_card_brand("4012888888881881") == "visa"

    def test_mastercard_detection(self):
        """Test Mastercard detection."""
        assert _detect_card_brand("5555555555554444") == "mastercard"
        assert _detect_card_brand("5105105105105100") == "mastercard"
        assert _detect_card_brand("2221000000000009") == "mastercard"  # New range

    def test_amex_detection(self):
        """Test American Express detection."""
        assert _detect_card_brand("378282246310005") == "amex"
        assert _detect_card_brand("371449635398431") == "amex"

    def test_discover_detection(self):
        """Test Discover card detection."""
        assert _detect_card_brand("6011111111111117") == "discover"
        assert _detect_card_brand("6011000990139424") == "discover"

    def test_unknown_card(self):
        """Test unknown card brand."""
        assert _detect_card_brand("9111111111111111") == "unknown"
        assert _detect_card_brand("") == "unknown"


class TestPaymentToken:
    """Tests for PaymentToken domain model."""

    def test_token_creation(self):
        """Test creating a payment token."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"encrypted-data",
            encryption_key_version="v1",
            device_token="device-456",
        )

        assert token.payment_token.startswith("pt_")
        assert token.restaurant_id == "rest-123"
        assert token.encrypted_payment_data == b"encrypted-data"
        assert token.encryption_key_version == "v1"
        assert token.device_token == "device-456"
        assert isinstance(token.created_at, datetime)
        assert isinstance(token.expires_at, datetime)
        assert token.expires_at > token.created_at

    def test_token_id_generation(self):
        """Test token ID format."""
        token_id = PaymentToken.generate_token_id()
        assert token_id.startswith("pt_")
        assert len(token_id) > 3

        # Each generated ID should be unique
        token_id2 = PaymentToken.generate_token_id()
        assert token_id != token_id2

    def test_token_expiration(self):
        """Test token expiration logic."""
        # Create token that expires in 1 hour
        now = datetime.utcnow()
        token = PaymentToken(
            payment_token="pt_test",
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        # Should not be expired
        assert not token.is_expired()

        # Create expired token
        expired_token = PaymentToken(
            payment_token="pt_test2",
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )

        # Should be expired
        assert expired_token.is_expired()

    def test_validate_ownership_success(self):
        """Test ownership validation with correct restaurant."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
        )

        # Should not raise
        token.validate_ownership("rest-123")

    def test_validate_ownership_failure(self):
        """Test ownership validation with wrong restaurant."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
        )

        # Should raise TokenOwnershipError
        with pytest.raises(TokenOwnershipError, match="does not belong"):
            token.validate_ownership("rest-999")

    def test_validate_not_expired_success(self):
        """Test expiration validation with valid token."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            expiration_hours=24,
        )

        # Should not raise
        token.validate_not_expired()

    def test_validate_not_expired_failure(self):
        """Test expiration validation with expired token."""
        now = datetime.utcnow()
        token = PaymentToken(
            payment_token="pt_test",
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            created_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),
        )

        # Should raise TokenExpiredError
        with pytest.raises(TokenExpiredError, match="expired at"):
            token.validate_not_expired()

    def test_custom_expiration_hours(self):
        """Test creating token with custom expiration."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            expiration_hours=48,
        )

        # Should expire in 48 hours
        expected_expiration = token.created_at + timedelta(hours=48)
        # Allow 1 second tolerance for test execution time
        assert abs((token.expires_at - expected_expiration).total_seconds()) < 1

    def test_token_validation_errors(self):
        """Test token field validation."""
        now = datetime.utcnow()

        # Invalid token format
        with pytest.raises(ValueError, match="must start with 'pt_'"):
            PaymentToken(
                payment_token="invalid_token",
                restaurant_id="rest-123",
                encrypted_payment_data=b"data",
                encryption_key_version="v1",
                device_token="device-456",
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )

        # Empty restaurant_id
        with pytest.raises(ValueError, match="restaurant_id cannot be empty"):
            PaymentToken(
                payment_token="pt_test",
                restaurant_id="",
                encrypted_payment_data=b"data",
                encryption_key_version="v1",
                device_token="device-456",
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )

        # Invalid expiration (expires_at before created_at)
        with pytest.raises(ValueError, match="must be after created_at"):
            PaymentToken(
                payment_token="pt_test",
                restaurant_id="rest-123",
                encrypted_payment_data=b"data",
                encryption_key_version="v1",
                device_token="device-456",
                created_at=now,
                expires_at=now - timedelta(hours=1),
            )


class TestTokenService:
    """Tests for TokenService domain service."""

    @pytest.fixture
    def service(self):
        """Create TokenService instance."""
        return TokenService()

    @pytest.fixture
    def sample_payment_data(self):
        """Create sample payment data."""
        return PaymentData(
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2025",
            cvv="123",
            cardholder_name="John Doe",
        )

    @pytest.fixture
    def bdk(self):
        """Generate Base Derivation Key."""
        return os.urandom(32)

    @pytest.fixture
    def service_key(self):
        """Generate service encryption key."""
        return os.urandom(32)

    def test_create_token_from_device_encrypted_data(
        self, service, sample_payment_data, bdk, service_key
    ):
        """Test complete token creation flow."""
        from payment_token.domain.encryption import encrypt_payment_data

        # Simulate device-encrypted data
        device_token = "device-12345"
        device_encrypted = encrypt_payment_data(
            sample_payment_data.to_bytes(), bdk, device_token
        )

        # Create token
        token = service.create_token_from_device_encrypted_data(
            restaurant_id="rest-123",
            encrypted_payment_data_from_device=device_encrypted,
            device_token=device_token,
            bdk=bdk,
            service_encryption_key=service_key,
            service_key_version="v1",
        )

        # Verify token
        assert token.payment_token.startswith("pt_")
        assert token.restaurant_id == "rest-123"
        assert token.device_token == device_token
        assert token.encryption_key_version == "v1"
        assert token.metadata.card_brand == "visa"
        assert token.metadata.last4 == "1111"

    def test_decrypt_token(self, service, sample_payment_data, service_key):
        """Test token decryption."""
        # Encrypt payment data
        encrypted_data = encrypt_with_key(sample_payment_data.to_bytes(), service_key)
        serialized = service._serialize_encrypted_data(encrypted_data)

        # Create token
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=serialized,
            encryption_key_version="v1",
            device_token="device-456",
        )

        # Decrypt
        decrypted = service.decrypt_token(token, service_key)

        # Verify
        assert decrypted.card_number == sample_payment_data.card_number
        assert decrypted.exp_month == sample_payment_data.exp_month
        assert decrypted.cvv == sample_payment_data.cvv

    def test_re_encrypt_token(self, service, sample_payment_data, service_key):
        """Test token re-encryption for key rotation."""
        # Create token with old key
        old_key = service_key
        encrypted_data = encrypt_with_key(sample_payment_data.to_bytes(), old_key)
        serialized = service._serialize_encrypted_data(encrypted_data)

        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=serialized,
            encryption_key_version="v1",
            device_token="device-456",
        )

        # Re-encrypt with new key
        new_key = os.urandom(32)
        updated_token = service.re_encrypt_token(
            token, old_service_key=old_key, new_service_key=new_key, new_key_version="v2"
        )

        # Verify key version updated
        assert updated_token.encryption_key_version == "v2"

        # Verify data can be decrypted with new key
        decrypted = service.decrypt_token(updated_token, new_key)
        assert decrypted.card_number == sample_payment_data.card_number

    def test_serialization_round_trip(self, service):
        """Test encrypted data serialization."""
        ciphertext = b"encrypted_content"
        nonce = os.urandom(12)
        encrypted = EncryptedData(ciphertext=ciphertext, nonce=nonce)

        # Serialize
        serialized = service._serialize_encrypted_data(encrypted)

        # Deserialize
        deserialized = service._deserialize_encrypted_data(serialized)

        # Verify
        assert deserialized.nonce == nonce
        assert deserialized.ciphertext == ciphertext


class TestValidateTokenForUse:
    """Tests for validate_token_for_use helper."""

    def test_valid_token(self):
        """Test validation with valid token."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
        )

        # Should not raise
        validate_token_for_use(token, "rest-123")

    def test_wrong_restaurant(self):
        """Test validation with wrong restaurant."""
        token = PaymentToken.create(
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
        )

        with pytest.raises(TokenOwnershipError):
            validate_token_for_use(token, "rest-999")

    def test_expired_token(self):
        """Test validation with expired token."""
        now = datetime.utcnow()
        token = PaymentToken(
            payment_token="pt_test",
            restaurant_id="rest-123",
            encrypted_payment_data=b"data",
            encryption_key_version="v1",
            device_token="device-456",
            created_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),
        )

        with pytest.raises(TokenExpiredError):
            validate_token_for_use(token, "rest-123")
