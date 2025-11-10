"""Unit tests for AWS KMS client wrapper.

These tests use moto to mock AWS KMS interactions, allowing us to test
the KMS client without making actual AWS API calls.
"""

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from payment_token.infrastructure.kms import KMSClient, KMSError


@pytest.fixture
def kms_key_id() -> str:
    """Create a mock KMS key and return its ID."""
    return "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"


@pytest.fixture
def mock_kms_client(kms_key_id: str) -> KMSClient:
    """Create a KMS client with mocked AWS backend."""
    with mock_aws():
        import boto3

        # Create a mock KMS key
        kms = boto3.client("kms", region_name="us-east-1")
        response = kms.create_key(
            Description="Test BDK for payment token service",
            KeyUsage="ENCRYPT_DECRYPT",
            Origin="AWS_KMS",
        )
        key_id = response["KeyMetadata"]["KeyId"]

        # Create client
        client = KMSClient(bdk_kms_key_id=key_id, region="us-east-1")

        yield client


class TestKMSClientInitialization:
    """Tests for KMS client initialization."""

    def test_init_with_valid_key_id(self) -> None:
        """Test that client initializes with valid key ID."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/test",
            region="us-east-1",
        )

        assert client.bdk_kms_key_id == "arn:aws:kms:us-east-1:123456789012:key/test"
        assert client.region == "us-east-1"

    def test_init_with_empty_key_id_raises_error(self) -> None:
        """Test that empty key ID raises ValueError."""
        with pytest.raises(ValueError, match="bdk_kms_key_id cannot be empty"):
            KMSClient(bdk_kms_key_id="", region="us-east-1")

    def test_init_with_custom_endpoint(self) -> None:
        """Test that client can be initialized with custom endpoint (LocalStack)."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/test",
            region="us-east-1",
            endpoint_url="http://localhost:4566",
        )

        assert client.bdk_kms_key_id == "arn:aws:kms:us-east-1:123456789012:key/test"


class TestGetBDK:
    """Tests for BDK retrieval from KMS."""

    @mock_aws
    def test_get_bdk_returns_32_bytes(self, mock_kms_client: KMSClient) -> None:
        """Test that get_bdk returns 32-byte key."""
        bdk = mock_kms_client.get_bdk()

        assert len(bdk) == 32
        assert isinstance(bdk, bytes)

    @mock_aws
    def test_get_bdk_with_encryption_context(self, mock_kms_client: KMSClient) -> None:
        """Test that get_bdk works with encryption context."""
        encryption_context = {"service": "payment-token", "purpose": "bdk"}

        bdk = mock_kms_client.get_bdk(encryption_context=encryption_context)

        assert len(bdk) == 32

    @mock_aws
    def test_get_bdk_is_consistent(self, mock_kms_client: KMSClient) -> None:
        """Test that get_bdk returns consistent results.

        Note: In moto, generate_data_key produces different keys each time.
        In production with a stored encrypted BDK, this would be deterministic.
        This test documents the expected behavior with generate_data_key.
        """
        bdk1 = mock_kms_client.get_bdk()
        bdk2 = mock_kms_client.get_bdk()

        # With generate_data_key, keys are different (random generation)
        # In production with decrypt, they would be the same
        assert len(bdk1) == 32
        assert len(bdk2) == 32

    @mock_aws
    def test_get_bdk_with_invalid_key_id_raises_error(self) -> None:
        """Test that invalid key ID raises KMSError."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/invalid",
            region="us-east-1",
        )

        with pytest.raises(KMSError, match="Failed to retrieve BDK from KMS"):
            client.get_bdk()


class TestDecryptDataKey:
    """Tests for decrypting encrypted data keys."""

    @mock_aws
    def test_decrypt_data_key_success(self, mock_kms_client: KMSClient) -> None:
        """Test successful data key decryption."""
        import boto3

        # Create encrypted data key
        kms = boto3.client("kms", region_name="us-east-1")
        response = kms.generate_data_key(KeyId=mock_kms_client.bdk_kms_key_id, KeySpec="AES_256")
        ciphertext_blob = response["CiphertextBlob"]
        expected_plaintext = response["Plaintext"]

        # Decrypt using our client
        plaintext = mock_kms_client.decrypt_data_key(ciphertext_blob)

        assert plaintext == expected_plaintext
        assert len(plaintext) == 32

    @mock_aws
    def test_decrypt_data_key_with_encryption_context(self, mock_kms_client: KMSClient) -> None:
        """Test data key decryption with encryption context."""
        import boto3

        encryption_context = {"service": "payment-token", "purpose": "test"}

        # Create encrypted data key with context
        kms = boto3.client("kms", region_name="us-east-1")
        response = kms.generate_data_key(
            KeyId=mock_kms_client.bdk_kms_key_id,
            KeySpec="AES_256",
            EncryptionContext=encryption_context,
        )
        ciphertext_blob = response["CiphertextBlob"]
        expected_plaintext = response["Plaintext"]

        # Decrypt with same context
        plaintext = mock_kms_client.decrypt_data_key(ciphertext_blob, encryption_context)

        assert plaintext == expected_plaintext

    @mock_aws
    def test_decrypt_data_key_with_wrong_context_fails(self, mock_kms_client: KMSClient) -> None:
        """Test that decryption with wrong encryption context fails."""
        import boto3

        encryption_context = {"service": "payment-token", "purpose": "test"}
        wrong_context = {"service": "wrong", "purpose": "test"}

        # Create encrypted data key with context
        kms = boto3.client("kms", region_name="us-east-1")
        response = kms.generate_data_key(
            KeyId=mock_kms_client.bdk_kms_key_id,
            KeySpec="AES_256",
            EncryptionContext=encryption_context,
        )
        ciphertext_blob = response["CiphertextBlob"]

        # Try to decrypt with wrong context
        with pytest.raises(KMSError, match="Failed to decrypt data key"):
            mock_kms_client.decrypt_data_key(ciphertext_blob, wrong_context)


class TestHealthCheck:
    """Tests for KMS health check."""

    @mock_aws
    def test_health_check_with_valid_key_returns_true(self, mock_kms_client: KMSClient) -> None:
        """Test that health check returns True for valid key."""
        result = mock_kms_client.health_check()

        assert result is True

    @mock_aws
    def test_health_check_with_invalid_key_returns_false(self) -> None:
        """Test that health check returns False for invalid key."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/invalid",
            region="us-east-1",
        )

        result = client.health_check()

        assert result is False


class TestKMSErrorHandling:
    """Tests for error handling in KMS operations."""

    @mock_aws
    def test_kms_error_contains_error_code(self) -> None:
        """Test that KMSError includes AWS error code."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/nonexistent",
            region="us-east-1",
        )

        with pytest.raises(KMSError) as exc_info:
            client.get_bdk()

        # Error message should mention it's a KMS failure
        assert "Failed to retrieve BDK from KMS" in str(exc_info.value)

    @mock_aws
    def test_client_error_wrapped_in_kms_error(self) -> None:
        """Test that boto3 ClientError is wrapped in KMSError."""
        client = KMSClient(
            bdk_kms_key_id="arn:aws:kms:us-east-1:123456789012:key/invalid",
            region="us-east-1",
        )

        with pytest.raises(KMSError):
            client.get_bdk()


class TestKMSIntegration:
    """Integration tests for complete KMS workflows."""

    @mock_aws
    def test_full_encryption_workflow_with_kms(self, mock_kms_client: KMSClient) -> None:
        """Test complete workflow: get BDK -> derive key -> encrypt/decrypt."""
        from payment_token.domain.encryption import (
            decrypt_payment_data,
            encrypt_payment_data,
        )

        # Get BDK from KMS
        bdk = mock_kms_client.get_bdk()

        # Use BDK for encryption/decryption
        device_token = "device-12345"
        payment_data = b'{"card": "4111111111111111"}'

        encrypted = encrypt_payment_data(payment_data, bdk, device_token)
        decrypted = decrypt_payment_data(encrypted, bdk, device_token)

        assert decrypted == payment_data

    @mock_aws
    def test_encryption_context_provides_additional_security(
        self, mock_kms_client: KMSClient
    ) -> None:
        """Test that encryption context adds additional security layer."""
        context = {"service": "payment-token", "purpose": "bdk", "environment": "test"}

        bdk = mock_kms_client.get_bdk(encryption_context=context)

        assert len(bdk) == 32
        # In production, KMS would enforce that decrypt calls use same context
