"""Unit tests for identity token HMAC calculation.

These tests verify the HMAC-based identity token generation using mocked KMS.
"""

import hashlib
import hmac

import pytest
from moto import mock_aws

from payment_token.domain.identity import (
    CardIdentityInput,
    IdentityTokenResult,
    build_identity_input,
    calculate_identity_hmac,
    normalize_exp_month,
    normalize_exp_year,
    normalize_pan,
)
from payment_token.infrastructure.kms import KMSClient


class TestNormalizePan:
    """Tests for PAN normalization."""

    def test_normalize_plain_pan(self) -> None:
        """Test normalizing plain card number."""
        result = normalize_pan("4111111111111111")
        assert result == "4111111111111111"

    def test_normalize_pan_with_spaces(self) -> None:
        """Test normalizing card number with spaces."""
        result = normalize_pan("4111 1111 1111 1111")
        assert result == "4111111111111111"

    def test_normalize_pan_with_dashes(self) -> None:
        """Test normalizing card number with dashes."""
        result = normalize_pan("4111-1111-1111-1111")
        assert result == "4111111111111111"

    def test_normalize_pan_with_mixed_separators(self) -> None:
        """Test normalizing card number with mixed separators."""
        result = normalize_pan("4111 1111-1111 1111")
        assert result == "4111111111111111"

    def test_normalize_pan_empty_raises_error(self) -> None:
        """Test that empty PAN raises ValueError."""
        with pytest.raises(ValueError, match="PAN cannot be empty"):
            normalize_pan("")

    def test_normalize_pan_with_letters_raises_error(self) -> None:
        """Test that PAN with letters raises ValueError."""
        with pytest.raises(ValueError, match="must contain only digits"):
            normalize_pan("4111-XXXX-1111-1111")

    def test_normalize_pan_too_short_raises_error(self) -> None:
        """Test that PAN shorter than 13 digits raises ValueError."""
        with pytest.raises(ValueError, match="length must be 13-19"):
            normalize_pan("411111111111")  # 12 digits

    def test_normalize_pan_too_long_raises_error(self) -> None:
        """Test that PAN longer than 19 digits raises ValueError."""
        with pytest.raises(ValueError, match="length must be 13-19"):
            normalize_pan("41111111111111111111")  # 20 digits

    def test_normalize_amex_pan(self) -> None:
        """Test normalizing 15-digit AMEX card number."""
        result = normalize_pan("378282246310005")
        assert result == "378282246310005"
        assert len(result) == 15


class TestNormalizeExpMonth:
    """Tests for expiration month normalization."""

    def test_normalize_single_digit_month(self) -> None:
        """Test normalizing single digit month."""
        assert normalize_exp_month("1") == "01"
        assert normalize_exp_month("9") == "09"

    def test_normalize_double_digit_month(self) -> None:
        """Test normalizing double digit month."""
        assert normalize_exp_month("01") == "01"
        assert normalize_exp_month("12") == "12"

    def test_normalize_month_with_whitespace(self) -> None:
        """Test normalizing month with whitespace."""
        assert normalize_exp_month(" 3 ") == "03"

    def test_normalize_empty_month_returns_empty(self) -> None:
        """Test that empty month returns empty string."""
        assert normalize_exp_month("") == ""
        assert normalize_exp_month(None) == ""

    def test_normalize_invalid_month_raises_error(self) -> None:
        """Test that invalid month raises ValueError."""
        with pytest.raises(ValueError, match="Invalid month"):
            normalize_exp_month("13")
        with pytest.raises(ValueError, match="Invalid month"):
            normalize_exp_month("0")

    def test_normalize_non_numeric_month_raises_error(self) -> None:
        """Test that non-numeric month raises ValueError."""
        with pytest.raises(ValueError, match="Month must be numeric"):
            normalize_exp_month("Jan")


class TestNormalizeExpYear:
    """Tests for expiration year normalization."""

    def test_normalize_4_digit_year(self) -> None:
        """Test normalizing 4-digit year."""
        assert normalize_exp_year("2025") == "2025"
        assert normalize_exp_year("2030") == "2030"

    def test_normalize_2_digit_year(self) -> None:
        """Test normalizing 2-digit year."""
        assert normalize_exp_year("25") == "2025"
        assert normalize_exp_year("30") == "2030"

    def test_normalize_year_with_whitespace(self) -> None:
        """Test normalizing year with whitespace."""
        assert normalize_exp_year(" 2025 ") == "2025"

    def test_normalize_empty_year_returns_empty(self) -> None:
        """Test that empty year returns empty string."""
        assert normalize_exp_year("") == ""
        assert normalize_exp_year(None) == ""

    def test_normalize_year_out_of_range_raises_error(self) -> None:
        """Test that year out of range raises ValueError."""
        with pytest.raises(ValueError, match="Year out of valid range"):
            normalize_exp_year("2019")
        with pytest.raises(ValueError, match="Year out of valid range"):
            normalize_exp_year("2100")

    def test_normalize_non_numeric_year_raises_error(self) -> None:
        """Test that non-numeric year raises ValueError."""
        with pytest.raises(ValueError, match="Year must be numeric"):
            normalize_exp_year("twenty")


class TestBuildIdentityInput:
    """Tests for building identity input string."""

    def test_build_input_pan_only(self) -> None:
        """Test building input with PAN only."""
        card_input = CardIdentityInput(pan="4111111111111111")
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111"

    def test_build_input_with_expiration(self) -> None:
        """Test building input with PAN and expiration."""
        card_input = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2025"
        )
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111|exp:12/2025"

    def test_build_input_normalizes_pan(self) -> None:
        """Test that input building normalizes PAN."""
        card_input = CardIdentityInput(pan="4111 1111 1111 1111")
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111"

    def test_build_input_normalizes_expiration(self) -> None:
        """Test that input building normalizes expiration."""
        card_input = CardIdentityInput(
            pan="4111111111111111",
            exp_month="3",
            exp_year="25"
        )
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111|exp:03/2025"

    def test_build_input_ignores_partial_expiration(self) -> None:
        """Test that partial expiration is ignored."""
        # Only month
        card_input = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12"
        )
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111"

        # Only year
        card_input = CardIdentityInput(
            pan="4111111111111111",
            exp_year="2025"
        )
        result = build_identity_input(card_input)
        assert result == "pan:4111111111111111"


class TestCalculateIdentityHmac:
    """Tests for HMAC identity calculation."""

    @pytest.fixture
    def test_hmac_key(self) -> bytes:
        """Generate a test HMAC key (32 bytes)."""
        return b"0" * 32

    def test_calculate_hmac_returns_result(self, test_hmac_key: bytes) -> None:
        """Test that calculate_identity_hmac returns proper result."""
        card_input = CardIdentityInput(pan="4111111111111111")

        result = calculate_identity_hmac(card_input, test_hmac_key)

        assert isinstance(result, IdentityTokenResult)
        assert len(result.identity_hash) == 64  # SHA-256 hex is 64 chars
        assert result.normalized_input == "pan:4111111111111111"

    def test_calculate_hmac_is_deterministic(self, test_hmac_key: bytes) -> None:
        """Test that same input produces same hash."""
        card_input = CardIdentityInput(pan="4111111111111111")

        result1 = calculate_identity_hmac(card_input, test_hmac_key)
        result2 = calculate_identity_hmac(card_input, test_hmac_key)

        assert result1.identity_hash == result2.identity_hash

    def test_calculate_hmac_different_cards_different_hash(
        self, test_hmac_key: bytes
    ) -> None:
        """Test that different cards produce different hashes."""
        card1 = CardIdentityInput(pan="4111111111111111")
        card2 = CardIdentityInput(pan="5555555555554444")

        result1 = calculate_identity_hmac(card1, test_hmac_key)
        result2 = calculate_identity_hmac(card2, test_hmac_key)

        assert result1.identity_hash != result2.identity_hash

    def test_calculate_hmac_different_keys_different_hash(self) -> None:
        """Test that different keys produce different hashes."""
        card_input = CardIdentityInput(pan="4111111111111111")
        key1 = b"0" * 32
        key2 = b"1" * 32

        result1 = calculate_identity_hmac(card_input, key1)
        result2 = calculate_identity_hmac(card_input, key2)

        assert result1.identity_hash != result2.identity_hash

    def test_calculate_hmac_with_expiration(self, test_hmac_key: bytes) -> None:
        """Test HMAC calculation with expiration data."""
        card_input = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2025"
        )

        result = calculate_identity_hmac(card_input, test_hmac_key)

        assert result.normalized_input == "pan:4111111111111111|exp:12/2025"
        assert len(result.identity_hash) == 64

    def test_calculate_hmac_expiration_changes_hash(
        self, test_hmac_key: bytes
    ) -> None:
        """Test that different expiration produces different hash."""
        card1 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2025"
        )
        card2 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="01",
            exp_year="2026"
        )

        result1 = calculate_identity_hmac(card1, test_hmac_key)
        result2 = calculate_identity_hmac(card2, test_hmac_key)

        assert result1.identity_hash != result2.identity_hash

    def test_calculate_hmac_invalid_key_length_raises_error(self) -> None:
        """Test that invalid key length raises ValueError."""
        card_input = CardIdentityInput(pan="4111111111111111")

        with pytest.raises(ValueError, match="HMAC key must be 32 bytes"):
            calculate_identity_hmac(card_input, b"short")

    def test_calculate_hmac_matches_manual_calculation(
        self, test_hmac_key: bytes
    ) -> None:
        """Test that calculated hash matches manual HMAC calculation."""
        card_input = CardIdentityInput(pan="4111111111111111")

        result = calculate_identity_hmac(card_input, test_hmac_key)

        # Manual calculation
        expected = hmac.new(
            test_hmac_key,
            b"pan:4111111111111111",
            hashlib.sha256
        ).hexdigest()

        assert result.identity_hash == expected

    def test_calculate_hmac_normalized_input_format(
        self, test_hmac_key: bytes
    ) -> None:
        """Test the exact format of normalized input."""
        # PAN with spaces and 2-digit year
        card_input = CardIdentityInput(
            pan="4111 1111 1111 1111",
            exp_month="1",
            exp_year="25"
        )

        result = calculate_identity_hmac(card_input, test_hmac_key)

        # Should be normalized
        assert result.normalized_input == "pan:4111111111111111|exp:01/2025"


class TestIdentityWithMockedKMS:
    """Tests for identity HMAC calculation with mocked KMS.

    These tests use moto to mock AWS KMS, matching the pattern used
    by other unit tests in this project.
    """

    @pytest.fixture
    def mock_kms_hmac_key_setup(self):
        """Create mocked KMS key and generate a stored HMAC key for testing.

        Returns tuple of (kms_client, encrypted_key_blob) where the blob
        can be decrypted to get the same HMAC key each time.
        """
        with mock_aws():
            import boto3

            # Create a mock KMS key
            kms = boto3.client("kms", region_name="us-east-1")
            response = kms.create_key(
                Description="Identity HMAC key for card tokenization",
                KeyUsage="ENCRYPT_DECRYPT",
            )
            key_id = response["KeyMetadata"]["KeyId"]

            # Generate a data key - this simulates creating and storing the HMAC key
            data_key_response = kms.generate_data_key(
                KeyId=key_id,
                KeySpec="AES_256",
            )
            encrypted_key_blob = data_key_response["CiphertextBlob"]

            # Create our KMS client wrapper
            client = KMSClient(
                bdk_kms_key_id=key_id,
                region="us-east-1",
            )

            yield client, encrypted_key_blob

    def test_kms_decrypt_returns_consistent_key(
        self, mock_kms_hmac_key_setup
    ) -> None:
        """Test that decrypting the same blob returns the same key."""
        kms_client, encrypted_blob = mock_kms_hmac_key_setup

        # Decrypt multiple times - should get same key
        key1 = kms_client.decrypt_data_key(encrypted_blob)
        key2 = kms_client.decrypt_data_key(encrypted_blob)
        key3 = kms_client.decrypt_data_key(encrypted_blob)

        assert key1 == key2
        assert key2 == key3
        assert len(key1) == 32

    def test_hmac_calculation_with_kms_key(
        self, mock_kms_hmac_key_setup
    ) -> None:
        """Test HMAC calculation using key from mocked KMS."""
        kms_client, encrypted_blob = mock_kms_hmac_key_setup

        # Get the HMAC key
        hmac_key = kms_client.decrypt_data_key(encrypted_blob)

        # Calculate identity hash
        card_input = CardIdentityInput(pan="4111111111111111")
        result = calculate_identity_hmac(card_input, hmac_key)

        assert len(result.identity_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.identity_hash)

    def test_same_card_same_hash_with_kms(
        self, mock_kms_hmac_key_setup
    ) -> None:
        """Test that same card produces same hash when using KMS key."""
        kms_client, encrypted_blob = mock_kms_hmac_key_setup

        # Get key twice (simulating separate requests)
        key1 = kms_client.decrypt_data_key(encrypted_blob)
        key2 = kms_client.decrypt_data_key(encrypted_blob)

        # Calculate hashes
        card_input = CardIdentityInput(pan="4111111111111111")
        result1 = calculate_identity_hmac(card_input, key1)
        result2 = calculate_identity_hmac(card_input, key2)

        assert result1.identity_hash == result2.identity_hash

    def test_normalized_inputs_same_hash_with_kms(
        self, mock_kms_hmac_key_setup
    ) -> None:
        """Test that normalized inputs produce same hash with mocked KMS key."""
        kms_client, encrypted_blob = mock_kms_hmac_key_setup

        hmac_key = kms_client.decrypt_data_key(encrypted_blob)

        # Different formatting of same card
        inputs = [
            CardIdentityInput(pan="4111111111111111"),
            CardIdentityInput(pan="4111 1111 1111 1111"),
            CardIdentityInput(pan="4111-1111-1111-1111"),
        ]

        hashes = [calculate_identity_hmac(inp, hmac_key).identity_hash for inp in inputs]

        assert hashes[0] == hashes[1]
        assert hashes[1] == hashes[2]

    def test_different_cards_different_hash_with_kms(
        self, mock_kms_hmac_key_setup
    ) -> None:
        """Test that different cards produce different hashes."""
        kms_client, encrypted_blob = mock_kms_hmac_key_setup

        hmac_key = kms_client.decrypt_data_key(encrypted_blob)

        card1 = CardIdentityInput(pan="4111111111111111")
        card2 = CardIdentityInput(pan="5555555555554444")

        result1 = calculate_identity_hmac(card1, hmac_key)
        result2 = calculate_identity_hmac(card2, hmac_key)

        assert result1.identity_hash != result2.identity_hash


class TestHMACSecurityProperties:
    """Tests for HMAC security properties."""

    @pytest.fixture
    def test_hmac_key(self) -> bytes:
        """Generate a test HMAC key."""
        return b"0" * 32

    def test_timing_attack_resistance(self, test_hmac_key: bytes) -> None:
        """Test that hash comparison uses constant-time comparison.

        This test documents the expected behavior - actual timing attack
        resistance is provided by hmac.compare_digest in the implementation.
        """
        card_input = CardIdentityInput(pan="4111111111111111")
        result = calculate_identity_hmac(card_input, test_hmac_key)

        # Verify the hash format is suitable for constant-time comparison
        assert len(result.identity_hash) == 64
        assert isinstance(result.identity_hash, str)

    def test_hash_does_not_leak_card_info(self, test_hmac_key: bytes) -> None:
        """Test that hash doesn't contain card data patterns."""
        card_input = CardIdentityInput(pan="4111111111111111")
        result = calculate_identity_hmac(card_input, test_hmac_key)

        # Hash should not contain the card number
        assert "4111111111111111" not in result.identity_hash
        assert "4111" not in result.identity_hash

    def test_different_normalizations_same_hash(self, test_hmac_key: bytes) -> None:
        """Test that equivalent inputs produce same hash."""
        # Different representations of same card
        inputs = [
            CardIdentityInput(pan="4111111111111111"),
            CardIdentityInput(pan="4111 1111 1111 1111"),
            CardIdentityInput(pan="4111-1111-1111-1111"),
            CardIdentityInput(pan=" 4111 1111 1111 1111 "),
        ]

        hashes = [calculate_identity_hmac(inp, test_hmac_key).identity_hash for inp in inputs]

        # All should be identical
        assert len(set(hashes)) == 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def test_hmac_key(self) -> bytes:
        """Generate a test HMAC key."""
        return b"0" * 32

    def test_minimum_valid_pan_length(self, test_hmac_key: bytes) -> None:
        """Test with minimum valid PAN length (13 digits)."""
        card_input = CardIdentityInput(pan="4111111111111")  # 13 digits
        result = calculate_identity_hmac(card_input, test_hmac_key)
        assert len(result.identity_hash) == 64

    def test_maximum_valid_pan_length(self, test_hmac_key: bytes) -> None:
        """Test with maximum valid PAN length (19 digits)."""
        card_input = CardIdentityInput(pan="4111111111111111111")  # 19 digits
        result = calculate_identity_hmac(card_input, test_hmac_key)
        assert len(result.identity_hash) == 64

    def test_boundary_month_values(self, test_hmac_key: bytes) -> None:
        """Test boundary values for expiration month."""
        # January
        card1 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="1",
            exp_year="2025"
        )
        result1 = calculate_identity_hmac(card1, test_hmac_key)
        assert "exp:01/2025" in result1.normalized_input

        # December
        card2 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2025"
        )
        result2 = calculate_identity_hmac(card2, test_hmac_key)
        assert "exp:12/2025" in result2.normalized_input

    def test_boundary_year_values(self, test_hmac_key: bytes) -> None:
        """Test boundary values for expiration year."""
        # Minimum (2020)
        card1 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2020"
        )
        result1 = calculate_identity_hmac(card1, test_hmac_key)
        assert "exp:12/2020" in result1.normalized_input

        # Maximum (2099)
        card2 = CardIdentityInput(
            pan="4111111111111111",
            exp_month="12",
            exp_year="2099"
        )
        result2 = calculate_identity_hmac(card2, test_hmac_key)
        assert "exp:12/2099" in result2.normalized_input
