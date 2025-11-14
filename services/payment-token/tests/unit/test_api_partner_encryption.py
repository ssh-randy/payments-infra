"""Unit tests for API Partner Encryption Key functionality."""

import base64
import os

import pytest

from payment_token.domain.encryption import (
    DecryptionError,
    EncryptedData,
    EncryptionError,
    EncryptionMetadata,
    decrypt_with_encryption_metadata,
    decrypt_with_key,
    encrypt_with_key,
    get_decryption_key,
)


class TestEncryptionMetadata:
    """Tests for EncryptionMetadata domain model."""

    def test_encryption_metadata_creation(self) -> None:
        """Test creating EncryptionMetadata with valid data."""
        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(b"123456789012").decode()
        )

        assert metadata.key_id == "primary"
        assert metadata.algorithm == "AES-256-GCM"
        assert len(metadata.iv) > 0

    def test_get_iv_bytes_decodes_base64(self) -> None:
        """Test that get_iv_bytes correctly decodes base64 IV."""
        iv_bytes = os.urandom(12)
        iv_base64 = base64.b64encode(iv_bytes).decode()

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=iv_base64
        )

        decoded_iv = metadata.get_iv_bytes()

        assert decoded_iv == iv_bytes
        assert len(decoded_iv) == 12

    def test_get_iv_bytes_with_invalid_base64_raises_error(self) -> None:
        """Test that invalid base64 IV raises ValueError."""
        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv="not-valid-base64!!!"
        )

        with pytest.raises(ValueError, match="Invalid base64 IV"):
            metadata.get_iv_bytes()

    def test_from_protobuf(self, mocker) -> None:
        """Test creating EncryptionMetadata from protobuf message."""
        # Mock protobuf message
        mock_pb = mocker.Mock()
        mock_pb.key_id = "primary"
        mock_pb.algorithm = "AES-256-GCM"
        mock_pb.iv = "dGVzdGl2MTIzNDU2"

        metadata = EncryptionMetadata.from_protobuf(mock_pb)

        assert metadata.key_id == "primary"
        assert metadata.algorithm == "AES-256-GCM"
        assert metadata.iv == "dGVzdGl2MTIzNDU2"


class TestGetDecryptionKey:
    """Tests for get_decryption_key() function."""

    def test_get_decryption_key_with_primary_returns_key(self, monkeypatch) -> None:
        """Test that 'primary' key_id returns the primary encryption key."""
        # Set up environment variable with 32-byte hex key
        test_key_hex = "0123456789abcdef" * 4  # 32 bytes = 64 hex chars
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        key = get_decryption_key("primary")

        assert len(key) == 32
        assert key == bytes.fromhex(test_key_hex)

    def test_get_decryption_key_with_demo_primary_returns_key(self, monkeypatch) -> None:
        """Test that 'demo-primary-key-001' returns the primary encryption key."""
        test_key_hex = "fedcba9876543210" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        key = get_decryption_key("demo-primary-key-001")

        assert len(key) == 32
        assert key == bytes.fromhex(test_key_hex)

    def test_get_decryption_key_without_env_var_raises_error(self, monkeypatch) -> None:
        """Test that missing PRIMARY_ENCRYPTION_KEY raises EncryptionError."""
        monkeypatch.delenv("PRIMARY_ENCRYPTION_KEY", raising=False)

        with pytest.raises(EncryptionError, match="PRIMARY_ENCRYPTION_KEY environment variable not set"):
            get_decryption_key("primary")

    def test_get_decryption_key_with_invalid_hex_raises_error(self, monkeypatch) -> None:
        """Test that invalid hex format raises EncryptionError."""
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", "not-valid-hex")

        with pytest.raises(EncryptionError, match="Invalid PRIMARY_ENCRYPTION_KEY format"):
            get_decryption_key("primary")

    def test_get_decryption_key_with_wrong_length_raises_error(self, monkeypatch) -> None:
        """Test that key with wrong length raises EncryptionError."""
        # 16 bytes instead of 32
        short_key_hex = "0123456789abcdef" * 2
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", short_key_hex)

        with pytest.raises(EncryptionError, match="Primary key must be 32 bytes"):
            get_decryption_key("primary")

    def test_get_decryption_key_with_unknown_key_id_raises_error(self, monkeypatch) -> None:
        """Test that unknown key_id raises ValueError."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        with pytest.raises(ValueError, match="Unknown or unsupported key_id"):
            get_decryption_key("unknown-key-id")

    def test_get_decryption_key_with_future_ak_prefix_raises_error(self, monkeypatch) -> None:
        """Test that ak_ prefix (Phase 2) currently raises ValueError."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        with pytest.raises(ValueError, match="Unknown or unsupported key_id"):
            get_decryption_key("ak_550e8400-e29b-41d4-a716-446655440000")

    def test_get_decryption_key_with_future_bdk_prefix_raises_error(self, monkeypatch) -> None:
        """Test that bdk_ prefix (future) currently raises ValueError."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        with pytest.raises(ValueError, match="Unknown or unsupported key_id"):
            get_decryption_key("bdk_terminal_001")


class TestDecryptWithEncryptionMetadata:
    """Tests for decrypt_with_encryption_metadata() function."""

    def test_decrypt_with_encryption_metadata_roundtrip(self, monkeypatch) -> None:
        """Test encrypting and decrypting with encryption metadata."""
        # Set up encryption key
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)
        encryption_key = bytes.fromhex(test_key_hex)

        # Original data
        plaintext = b"sensitive payment card data"

        # Encrypt
        encrypted_data = encrypt_with_key(plaintext, encryption_key)

        # Create encryption metadata
        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        # Decrypt using encryption metadata
        decrypted = decrypt_with_encryption_metadata(
            encrypted_data.ciphertext,
            metadata
        )

        assert decrypted == plaintext

    def test_decrypt_with_wrong_algorithm_raises_error(self, monkeypatch) -> None:
        """Test that unsupported algorithm raises ValueError."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-128-CBC",  # Unsupported
            iv=base64.b64encode(os.urandom(12)).decode()
        )

        with pytest.raises(ValueError, match="Unsupported encryption algorithm"):
            decrypt_with_encryption_metadata(b"fake ciphertext", metadata)

    def test_decrypt_with_invalid_key_id_raises_error(self, monkeypatch) -> None:
        """Test that invalid key_id raises appropriate error."""
        monkeypatch.delenv("PRIMARY_ENCRYPTION_KEY", raising=False)

        metadata = EncryptionMetadata(
            key_id="invalid-key",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(os.urandom(12)).decode()
        )

        with pytest.raises(ValueError, match="Unknown or unsupported key_id"):
            decrypt_with_encryption_metadata(b"fake ciphertext", metadata)

    def test_decrypt_with_invalid_base64_iv_raises_error(self, monkeypatch) -> None:
        """Test that invalid base64 IV raises ValueError."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv="not-valid-base64!!!"
        )

        with pytest.raises(ValueError, match="Invalid base64 IV"):
            decrypt_with_encryption_metadata(b"fake ciphertext", metadata)

    def test_decrypt_with_wrong_key_raises_decryption_error(self, monkeypatch) -> None:
        """Test that decryption with wrong key fails."""
        # Encrypt with one key
        key1_hex = "0123456789abcdef" * 4
        key1 = bytes.fromhex(key1_hex)
        plaintext = b"sensitive data"
        encrypted_data = encrypt_with_key(plaintext, key1)

        # Try to decrypt with different key
        key2_hex = "fedcba9876543210" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", key2_hex)

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        with pytest.raises(DecryptionError, match="Failed to decrypt"):
            decrypt_with_encryption_metadata(encrypted_data.ciphertext, metadata)

    def test_decrypt_with_tampered_ciphertext_raises_error(self, monkeypatch) -> None:
        """Test that tampered ciphertext fails authentication."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)
        encryption_key = bytes.fromhex(test_key_hex)

        plaintext = b"sensitive data"
        encrypted_data = encrypt_with_key(plaintext, encryption_key)

        # Tamper with ciphertext
        tampered_ciphertext = bytearray(encrypted_data.ciphertext)
        tampered_ciphertext[0] ^= 0xFF

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        with pytest.raises(DecryptionError):
            decrypt_with_encryption_metadata(bytes(tampered_ciphertext), metadata)

    def test_decrypt_with_demo_primary_key_001(self, monkeypatch) -> None:
        """Test that demo-primary-key-001 key_id works."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)
        encryption_key = bytes.fromhex(test_key_hex)

        plaintext = b"test data"
        encrypted_data = encrypt_with_key(plaintext, encryption_key)

        metadata = EncryptionMetadata(
            key_id="demo-primary-key-001",  # Alternative key_id
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted_data.nonce).decode()
        )

        decrypted = decrypt_with_encryption_metadata(
            encrypted_data.ciphertext,
            metadata
        )

        assert decrypted == plaintext

    def test_decrypt_empty_ciphertext_fails(self, monkeypatch) -> None:
        """Test that decrypting empty ciphertext fails."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)

        metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(os.urandom(12)).decode()
        )

        # Empty ciphertext raises ValueError (before decryption attempt)
        with pytest.raises(ValueError, match="Ciphertext cannot be empty"):
            decrypt_with_encryption_metadata(b"", metadata)


class TestAPIPartnerKeyIntegration:
    """Integration tests for API partner key flow with real encryption."""

    def test_complete_encryption_decryption_flow(self, monkeypatch) -> None:
        """Test complete flow: encrypt on frontend, decrypt on backend."""
        # Simulate frontend encryption
        shared_key_hex = "0123456789abcdef" * 4
        shared_key = bytes.fromhex(shared_key_hex)

        # Frontend encrypts payment data
        payment_data = b'{"card_number":"4532123456789012","cvv":"123"}'
        iv = os.urandom(12)
        encrypted = encrypt_with_key(payment_data, shared_key)

        # Create metadata that frontend would send
        frontend_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(iv).decode()
        )

        # Backend receives encrypted data and metadata
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", shared_key_hex)

        # Use the actual nonce from encryption for proper test
        backend_metadata = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted.nonce).decode()
        )

        # Backend decrypts
        decrypted = decrypt_with_encryption_metadata(
            encrypted.ciphertext,
            backend_metadata
        )

        assert decrypted == payment_data

    def test_multiple_encryptions_with_different_ivs(self, monkeypatch) -> None:
        """Test that same data encrypted multiple times produces different ciphertexts."""
        test_key_hex = "0123456789abcdef" * 4
        monkeypatch.setenv("PRIMARY_ENCRYPTION_KEY", test_key_hex)
        encryption_key = bytes.fromhex(test_key_hex)

        plaintext = b"same payment data"

        # Encrypt twice
        encrypted1 = encrypt_with_key(plaintext, encryption_key)
        encrypted2 = encrypt_with_key(plaintext, encryption_key)

        # Different IVs
        assert encrypted1.nonce != encrypted2.nonce
        # Different ciphertexts
        assert encrypted1.ciphertext != encrypted2.ciphertext

        # But both decrypt correctly
        metadata1 = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted1.nonce).decode()
        )
        metadata2 = EncryptionMetadata(
            key_id="primary",
            algorithm="AES-256-GCM",
            iv=base64.b64encode(encrypted2.nonce).decode()
        )

        decrypted1 = decrypt_with_encryption_metadata(encrypted1.ciphertext, metadata1)
        decrypted2 = decrypt_with_encryption_metadata(encrypted2.ciphertext, metadata2)

        assert decrypted1 == plaintext
        assert decrypted2 == plaintext
