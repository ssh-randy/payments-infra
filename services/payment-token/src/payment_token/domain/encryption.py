"""Encryption and key derivation functions for payment token service.

This module implements HKDF-based key derivation and AES-GCM encryption
for secure payment data handling. All cryptographic operations follow
PCI DSS requirements and industry best practices.
"""

import base64
import logging
import os
from typing import NamedTuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Base exception for encryption-related errors."""

    pass


class DecryptionError(Exception):
    """Exception raised when decryption fails."""

    pass


class EncryptedData(NamedTuple):
    """Container for encrypted data and associated metadata."""

    ciphertext: bytes
    nonce: bytes  # Initialization vector for AES-GCM


class EncryptionMetadata(NamedTuple):
    """Metadata about encryption method used for API partner keys.

    This is used when payment data is encrypted with API partner keys
    (online ordering flow) instead of BDK-based device encryption.

    Attributes:
        key_id: Key identifier (e.g., "primary", "ak_{uuid}", "bdk_{id}")
        algorithm: Encryption algorithm (e.g., "AES-256-GCM")
        iv: Base64-encoded initialization vector
    """

    key_id: str
    algorithm: str
    iv: str  # Base64-encoded

    @classmethod
    def from_protobuf(cls, pb_metadata) -> "EncryptionMetadata":
        """Create from protobuf EncryptionMetadata message.

        Args:
            pb_metadata: Protobuf EncryptionMetadata message

        Returns:
            EncryptionMetadata instance
        """
        return cls(
            key_id=pb_metadata.key_id,
            algorithm=pb_metadata.algorithm,
            iv=pb_metadata.iv,
        )

    def get_iv_bytes(self) -> bytes:
        """Decode base64 IV to bytes.

        Returns:
            IV as bytes

        Raises:
            ValueError: If IV is not valid base64
        """
        try:
            return base64.b64decode(self.iv)
        except Exception as e:
            raise ValueError(f"Invalid base64 IV: {e}") from e


def derive_device_key(bdk: bytes, device_token: str) -> bytes:
    """Derive device-specific encryption key from BDK using HKDF.

    This function implements RFC 5869 HKDF (HMAC-based Key Derivation Function)
    to derive a unique encryption key for each device. The derived key is
    deterministic - the same BDK and device_token will always produce the
    same device key.

    Args:
        bdk: Base Derivation Key (32 bytes) from AWS KMS
        device_token: Device identifier string

    Returns:
        32-byte AES-256 encryption key

    Raises:
        ValueError: If bdk is not 32 bytes or device_token is empty
        EncryptionError: If key derivation fails

    Example:
        >>> bdk = os.urandom(32)  # From KMS in production
        >>> device_key = derive_device_key(bdk, "device-12345")
        >>> len(device_key)
        32

    Security notes:
        - Uses SHA-256 as the hash function
        - No salt (salt=None) as per spec
        - Info parameter includes version prefix for key rotation support
        - Derived keys should be cleared from memory after use
    """
    if not bdk:
        raise ValueError("BDK cannot be empty")

    if len(bdk) != 32:
        raise ValueError(f"BDK must be 32 bytes, got {len(bdk)}")

    if not device_token:
        raise ValueError("device_token cannot be empty")

    try:
        # HKDF configuration per spec
        info = b"payment-token-v1:" + device_token.encode("utf-8")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=None,  # No salt as per spec
            info=info,
        )

        device_key = hkdf.derive(bdk)

        logger.debug(f"Derived device key for token (length: {len(device_key)} bytes)")
        return device_key

    except Exception as e:
        logger.error(f"Key derivation failed: {str(e)}")
        raise EncryptionError(f"Failed to derive device key: {str(e)}") from e


def encrypt_with_key(plaintext: bytes, key: bytes) -> EncryptedData:
    """Encrypt data using AES-256-GCM with provided key.

    AES-GCM provides both confidentiality and authenticity (AEAD - Authenticated
    Encryption with Associated Data). This prevents tampering and ensures
    data integrity.

    Args:
        plaintext: Data to encrypt
        key: 32-byte AES-256 encryption key

    Returns:
        EncryptedData containing ciphertext and nonce

    Raises:
        ValueError: If key is not 32 bytes
        EncryptionError: If encryption fails

    Security notes:
        - Uses 96-bit (12-byte) nonce as recommended for GCM
        - Nonce is randomly generated for each encryption
        - Authentication tag is included in ciphertext (16 bytes)
    """
    if len(key) != 32:
        raise ValueError(f"Encryption key must be 32 bytes, got {len(key)}")

    if not plaintext:
        raise ValueError("Plaintext cannot be empty")

    try:
        # Generate random nonce (96 bits recommended for GCM)
        nonce = os.urandom(12)

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Encrypt (includes authentication tag)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)

        logger.debug(f"Encrypted {len(plaintext)} bytes -> {len(ciphertext)} bytes")
        return EncryptedData(ciphertext=ciphertext, nonce=nonce)

    except Exception as e:
        logger.error(f"Encryption failed: {str(e)}")
        raise EncryptionError(f"Failed to encrypt data: {str(e)}") from e


def decrypt_with_key(encrypted_data: EncryptedData, key: bytes) -> bytes:
    """Decrypt AES-256-GCM encrypted data.

    Args:
        encrypted_data: EncryptedData containing ciphertext and nonce
        key: 32-byte AES-256 decryption key (same as encryption key)

    Returns:
        Decrypted plaintext bytes

    Raises:
        ValueError: If key is not 32 bytes
        DecryptionError: If decryption or authentication fails

    Security notes:
        - Authentication tag is verified automatically
        - Decryption fails if data was tampered with
        - Decryption fails if wrong key is used
    """
    if len(key) != 32:
        raise ValueError(f"Decryption key must be 32 bytes, got {len(key)}")

    if not encrypted_data.ciphertext:
        raise ValueError("Ciphertext cannot be empty")

    if len(encrypted_data.nonce) != 12:
        raise ValueError(f"Nonce must be 12 bytes, got {len(encrypted_data.nonce)}")

    try:
        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Decrypt and verify authentication tag
        plaintext = aesgcm.decrypt(encrypted_data.nonce, encrypted_data.ciphertext, associated_data=None)

        logger.debug(f"Decrypted {len(encrypted_data.ciphertext)} bytes -> {len(plaintext)} bytes")
        return plaintext

    except Exception as e:
        # Don't expose detailed error messages for security
        logger.error(f"Decryption failed: {type(e).__name__}")
        raise DecryptionError("Failed to decrypt data - invalid key or corrupted data") from e


def encrypt_payment_data(
    payment_data: bytes, bdk: bytes, device_token: str
) -> EncryptedData:
    """Encrypt payment data using device-derived key.

    This is a convenience function that combines key derivation and encryption.
    Use this when you have the BDK and need to encrypt data for a specific device.

    Args:
        payment_data: Raw payment data to encrypt
        bdk: Base Derivation Key from KMS
        device_token: Device identifier

    Returns:
        EncryptedData containing encrypted payment data

    Raises:
        ValueError: If inputs are invalid
        EncryptionError: If encryption fails
    """
    device_key = derive_device_key(bdk, device_token)
    try:
        return encrypt_with_key(payment_data, device_key)
    finally:
        # Clear sensitive key from memory
        # Note: This is a best-effort attempt; Python's memory management
        # doesn't guarantee immediate cleanup
        del device_key


def decrypt_payment_data(
    encrypted_data: EncryptedData, bdk: bytes, device_token: str
) -> bytes:
    """Decrypt payment data using device-derived key.

    This is a convenience function that combines key derivation and decryption.
    Use this when you have the BDK and need to decrypt data from a specific device.

    Args:
        encrypted_data: EncryptedData from device
        bdk: Base Derivation Key from KMS
        device_token: Device identifier

    Returns:
        Decrypted payment data bytes

    Raises:
        ValueError: If inputs are invalid
        DecryptionError: If decryption fails
    """
    device_key = derive_device_key(bdk, device_token)
    try:
        return decrypt_with_key(encrypted_data, device_key)
    finally:
        # Clear sensitive key from memory
        del device_key


def generate_service_key() -> bytes:
    """Generate a new service encryption key for rotating keys.

    This generates a fresh 32-byte key for service-level encryption
    (re-encryption after device-level decryption).

    Returns:
        32-byte random encryption key

    Security note:
        This key should be encrypted with KMS before storage.
    """
    return os.urandom(32)


def get_decryption_key(key_id: str) -> bytes:
    """Look up decryption key by key_id.

    This function implements the multi-flow encryption architecture routing:
    - "primary" or "demo-primary-key-001": Primary demo key (Phase 1)
    - "ak_{uuid}": API partner keys for online ordering (Phase 2 - future)
    - "bdk_{identifier}": BDK-based keys for POS terminals (future)

    Phase 1 Implementation:
        Currently supports only the primary demo key. This unblocks frontend
        demo and establishes the routing architecture for future phases.

    Args:
        key_id: Key identifier from EncryptionMetadata

    Returns:
        32-byte decryption key

    Raises:
        ValueError: If key_id is unknown or unsupported
        EncryptionError: If key retrieval fails

    Security notes:
        - Phase 1: Primary key is retrieved from environment/KMS
        - Phase 2: API partner keys will be retrieved from database + KMS
        - Future: BDK keys will use key derivation
    """
    logger.debug(f"Looking up decryption key for key_id: {key_id}")

    # Phase 1: Support primary demo key
    if key_id in ("demo-primary-key-001", "primary"):
        # Get primary key from environment variable for demo
        # In production, this would be retrieved from KMS
        primary_key_hex = os.environ.get("PRIMARY_ENCRYPTION_KEY")

        if not primary_key_hex:
            raise EncryptionError(
                "PRIMARY_ENCRYPTION_KEY environment variable not set. "
                "This is required for API partner key encryption demo."
            )

        try:
            # Decode hex key to bytes
            key = bytes.fromhex(primary_key_hex)
            if len(key) != 32:
                raise ValueError(f"Primary key must be 32 bytes, got {len(key)}")
            logger.debug(f"Retrieved primary decryption key (length: {len(key)} bytes)")
            return key
        except ValueError as e:
            raise EncryptionError(f"Invalid PRIMARY_ENCRYPTION_KEY format: {e}") from e

    # Future Phase 2: API partner keys
    # if key_id.startswith("ak_"):
    #     # Look up in database and decrypt with KMS
    #     return await get_api_partner_key(key_id)

    # Future: BDK-based keys for POS terminals
    # if key_id.startswith("bdk_"):
    #     # Derive key using BDK
    #     return await derive_bdk_key(key_id)

    # Unknown key_id format
    raise ValueError(
        f"Unknown or unsupported key_id: {key_id}. "
        f"Supported formats: 'primary', 'demo-primary-key-001' (Phase 1). "
        f"Future: 'ak_{{uuid}}' (API partner), 'bdk_{{id}}' (POS terminals)"
    )


def decrypt_with_encryption_metadata(
    encrypted_data: bytes, encryption_metadata: EncryptionMetadata
) -> bytes:
    """Decrypt payment data using encryption metadata (API partner key flow).

    This function is used when payment data is encrypted with API partner keys
    (online ordering) instead of BDK-based device encryption (POS terminals).

    Args:
        encrypted_data: Encrypted payment data bytes
        encryption_metadata: Metadata containing key_id, algorithm, and IV

    Returns:
        Decrypted payment data bytes

    Raises:
        ValueError: If inputs are invalid or algorithm is unsupported
        DecryptionError: If decryption fails
        EncryptionError: If key retrieval fails

    Security notes:
        - Verifies algorithm is AES-256-GCM
        - Uses key_id to route to correct decryption method
        - IV is provided in metadata (not prepended to ciphertext)
    """
    logger.info(f"Decrypting with API partner key: {encryption_metadata.key_id}")

    # Validate algorithm
    if encryption_metadata.algorithm != "AES-256-GCM":
        raise ValueError(
            f"Unsupported encryption algorithm: {encryption_metadata.algorithm}. "
            f"Only AES-256-GCM is supported."
        )

    # Look up decryption key by key_id
    try:
        decryption_key = get_decryption_key(encryption_metadata.key_id)
    except (ValueError, EncryptionError) as e:
        logger.error(f"Failed to retrieve decryption key: {e}")
        raise

    # Decode IV from base64
    try:
        iv = encryption_metadata.get_iv_bytes()
    except ValueError as e:
        logger.error(f"Invalid IV in encryption metadata: {e}")
        raise

    # Create EncryptedData with ciphertext and IV
    encrypted = EncryptedData(ciphertext=encrypted_data, nonce=iv)

    # Decrypt using standard decrypt_with_key function
    try:
        plaintext = decrypt_with_key(encrypted, decryption_key)
        logger.debug(f"Successfully decrypted {len(encrypted_data)} bytes")
        return plaintext
    except DecryptionError as e:
        logger.error(f"Decryption failed with key {encryption_metadata.key_id}: {e}")
        raise
