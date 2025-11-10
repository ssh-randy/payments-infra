"""Unit tests for encryption and key derivation functions."""

import os

import pytest

from payment_token.domain.encryption import (
    DecryptionError,
    EncryptedData,
    EncryptionError,
    decrypt_payment_data,
    decrypt_with_key,
    derive_device_key,
    encrypt_payment_data,
    encrypt_with_key,
    generate_service_key,
)


class TestDeriveDeviceKey:
    """Tests for HKDF-based device key derivation."""

    def test_derive_device_key_produces_32_bytes(self) -> None:
        """Test that derived key is 32 bytes (AES-256)."""
        bdk = os.urandom(32)
        device_token = "device-12345"

        device_key = derive_device_key(bdk, device_token)

        assert len(device_key) == 32

    def test_derive_device_key_is_deterministic(self) -> None:
        """Test that same inputs produce same output (deterministic)."""
        bdk = os.urandom(32)
        device_token = "device-12345"

        key1 = derive_device_key(bdk, device_token)
        key2 = derive_device_key(bdk, device_token)

        assert key1 == key2

    def test_different_device_tokens_produce_different_keys(self) -> None:
        """Test that different device tokens produce different keys."""
        bdk = os.urandom(32)

        key1 = derive_device_key(bdk, "device-1")
        key2 = derive_device_key(bdk, "device-2")

        assert key1 != key2

    def test_different_bdks_produce_different_keys(self) -> None:
        """Test that different BDKs produce different keys."""
        bdk1 = os.urandom(32)
        bdk2 = os.urandom(32)
        device_token = "device-12345"

        key1 = derive_device_key(bdk1, device_token)
        key2 = derive_device_key(bdk2, device_token)

        assert key1 != key2

    def test_derive_device_key_empty_bdk_raises_error(self) -> None:
        """Test that empty BDK raises ValueError."""
        with pytest.raises(ValueError, match="BDK cannot be empty"):
            derive_device_key(b"", "device-12345")

    def test_derive_device_key_wrong_bdk_length_raises_error(self) -> None:
        """Test that BDK with wrong length raises ValueError."""
        bdk = os.urandom(16)  # Wrong length (should be 32)

        with pytest.raises(ValueError, match="BDK must be 32 bytes"):
            derive_device_key(bdk, "device-12345")

    def test_derive_device_key_empty_device_token_raises_error(self) -> None:
        """Test that empty device token raises ValueError."""
        bdk = os.urandom(32)

        with pytest.raises(ValueError, match="device_token cannot be empty"):
            derive_device_key(bdk, "")

    def test_derive_device_key_with_special_characters(self) -> None:
        """Test that device tokens with special characters work correctly."""
        bdk = os.urandom(32)
        device_token = "device-!@#$%^&*()_+-=[]{}|;:,.<>?"

        device_key = derive_device_key(bdk, device_token)

        assert len(device_key) == 32

    def test_derive_device_key_with_unicode(self) -> None:
        """Test that device tokens with unicode characters work correctly."""
        bdk = os.urandom(32)
        device_token = "device-你好-مرحبا"

        device_key = derive_device_key(bdk, device_token)

        assert len(device_key) == 32


class TestEncryptDecrypt:
    """Tests for AES-GCM encryption and decryption."""

    def test_encrypt_produces_encrypted_data(self) -> None:
        """Test that encryption produces EncryptedData with ciphertext and nonce."""
        key = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted = encrypt_with_key(plaintext, key)

        assert isinstance(encrypted, EncryptedData)
        assert len(encrypted.ciphertext) > 0
        assert len(encrypted.nonce) == 12  # GCM nonce is 96 bits (12 bytes)
        assert encrypted.ciphertext != plaintext  # Ensure it's actually encrypted

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test that encryption followed by decryption recovers original data."""
        key = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted = encrypt_with_key(plaintext, key)
        decrypted = decrypt_with_key(encrypted, key)

        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_fails(self) -> None:
        """Test that decryption with wrong key raises DecryptionError."""
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted = encrypt_with_key(plaintext, key1)

        with pytest.raises(DecryptionError, match="Failed to decrypt"):
            decrypt_with_key(encrypted, key2)

    def test_decrypt_with_modified_ciphertext_fails(self) -> None:
        """Test that decryption with modified ciphertext raises DecryptionError."""
        key = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted = encrypt_with_key(plaintext, key)

        # Tamper with ciphertext
        tampered_ciphertext = bytearray(encrypted.ciphertext)
        tampered_ciphertext[0] ^= 0xFF  # Flip bits
        tampered = EncryptedData(ciphertext=bytes(tampered_ciphertext), nonce=encrypted.nonce)

        with pytest.raises(DecryptionError, match="Failed to decrypt"):
            decrypt_with_key(tampered, key)

    def test_decrypt_with_modified_nonce_fails(self) -> None:
        """Test that decryption with modified nonce raises DecryptionError."""
        key = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted = encrypt_with_key(plaintext, key)

        # Tamper with nonce
        tampered_nonce = bytearray(encrypted.nonce)
        tampered_nonce[0] ^= 0xFF  # Flip bits
        tampered = EncryptedData(ciphertext=encrypted.ciphertext, nonce=bytes(tampered_nonce))

        with pytest.raises(DecryptionError, match="Failed to decrypt"):
            decrypt_with_key(tampered, key)

    def test_encrypt_with_wrong_key_length_raises_error(self) -> None:
        """Test that encryption with wrong key length raises ValueError."""
        key = os.urandom(16)  # Wrong length (should be 32)
        plaintext = b"sensitive payment data"

        with pytest.raises(ValueError, match="Encryption key must be 32 bytes"):
            encrypt_with_key(plaintext, key)

    def test_decrypt_with_wrong_key_length_raises_error(self) -> None:
        """Test that decryption with wrong key length raises ValueError."""
        key = os.urandom(16)  # Wrong length
        encrypted = EncryptedData(ciphertext=b"fake", nonce=os.urandom(12))

        with pytest.raises(ValueError, match="Decryption key must be 32 bytes"):
            decrypt_with_key(encrypted, key)

    def test_encrypt_empty_plaintext_raises_error(self) -> None:
        """Test that encrypting empty plaintext raises ValueError."""
        key = os.urandom(32)

        with pytest.raises(ValueError, match="Plaintext cannot be empty"):
            encrypt_with_key(b"", key)

    def test_decrypt_empty_ciphertext_raises_error(self) -> None:
        """Test that decrypting empty ciphertext raises ValueError."""
        key = os.urandom(32)
        encrypted = EncryptedData(ciphertext=b"", nonce=os.urandom(12))

        with pytest.raises(ValueError, match="Ciphertext cannot be empty"):
            decrypt_with_key(encrypted, key)

    def test_different_nonces_produce_different_ciphertexts(self) -> None:
        """Test that encrypting same data twice produces different ciphertexts (due to random nonce)."""
        key = os.urandom(32)
        plaintext = b"sensitive payment data"

        encrypted1 = encrypt_with_key(plaintext, key)
        encrypted2 = encrypt_with_key(plaintext, key)

        # Different nonces
        assert encrypted1.nonce != encrypted2.nonce
        # Different ciphertexts
        assert encrypted1.ciphertext != encrypted2.ciphertext

        # But both decrypt to same plaintext
        assert decrypt_with_key(encrypted1, key) == plaintext
        assert decrypt_with_key(encrypted2, key) == plaintext


class TestPaymentDataEncryptionDecryption:
    """Tests for high-level payment data encryption/decryption."""

    def test_encrypt_decrypt_payment_data_roundtrip(self) -> None:
        """Test complete payment data encryption/decryption flow."""
        bdk = os.urandom(32)
        device_token = "device-12345"
        payment_data = b'{"card_number": "4111111111111111", "cvv": "123"}'

        encrypted = encrypt_payment_data(payment_data, bdk, device_token)
        decrypted = decrypt_payment_data(encrypted, bdk, device_token)

        assert decrypted == payment_data

    def test_decrypt_payment_data_with_wrong_device_token_fails(self) -> None:
        """Test that decryption with wrong device token fails."""
        bdk = os.urandom(32)
        payment_data = b"sensitive payment data"

        encrypted = encrypt_payment_data(payment_data, bdk, "device-1")

        with pytest.raises(DecryptionError):
            decrypt_payment_data(encrypted, bdk, "device-2")

    def test_decrypt_payment_data_with_wrong_bdk_fails(self) -> None:
        """Test that decryption with wrong BDK fails."""
        bdk1 = os.urandom(32)
        bdk2 = os.urandom(32)
        device_token = "device-12345"
        payment_data = b"sensitive payment data"

        encrypted = encrypt_payment_data(payment_data, bdk1, device_token)

        with pytest.raises(DecryptionError):
            decrypt_payment_data(encrypted, bdk2, device_token)


class TestGenerateServiceKey:
    """Tests for service key generation."""

    def test_generate_service_key_produces_32_bytes(self) -> None:
        """Test that generated service key is 32 bytes."""
        key = generate_service_key()

        assert len(key) == 32

    def test_generate_service_key_produces_unique_keys(self) -> None:
        """Test that each call produces a unique key."""
        key1 = generate_service_key()
        key2 = generate_service_key()

        assert key1 != key2

    def test_generated_service_key_can_encrypt_decrypt(self) -> None:
        """Test that generated service key can be used for encryption/decryption."""
        key = generate_service_key()
        plaintext = b"test data"

        encrypted = encrypt_with_key(plaintext, key)
        decrypted = decrypt_with_key(encrypted, key)

        assert decrypted == plaintext
