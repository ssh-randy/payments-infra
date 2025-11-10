"""Domain services for payment token business logic.

This module contains the core business logic for token creation, decryption,
and re-encryption. It orchestrates the domain models and encryption functions
to implement the payment token service's business rules.
"""

import logging
from typing import Optional

from payment_token.domain.encryption import (
    DecryptionError,
    EncryptedData,
    EncryptionError,
    decrypt_payment_data,
    decrypt_with_key,
    encrypt_with_key,
)
from payment_token.domain.token import (
    PaymentData,
    PaymentToken,
    TokenError,
    TokenMetadata,
)

logger = logging.getLogger(__name__)


class TokenService:
    """Domain service for payment token operations.

    This service encapsulates the core business logic for creating and
    managing payment tokens. It handles device-based decryption and
    re-encryption with rotating service keys.

    Business Rules Implemented:
    - B1: Idempotency (handled at application layer)
    - B2: Device-based decryption with derived keys
    - B3: Re-encryption with rotating service keys
    - B4: Token expiration (default 24 hours)
    - B5: Restaurant scoping
    """

    def create_token_from_device_encrypted_data(
        self,
        restaurant_id: str,
        encrypted_payment_data_from_device: EncryptedData,
        device_token: str,
        bdk: bytes,
        service_encryption_key: bytes,
        service_key_version: str,
        metadata_dict: Optional[dict] = None,
        expiration_hours: int = 24,
    ) -> PaymentToken:
        """Create a payment token from device-encrypted data.

        This implements the complete token creation flow:
        1. Decrypt device-encrypted data using device-derived key (from BDK)
        2. Parse decrypted bytes into PaymentData domain object
        3. Extract metadata from payment data
        4. Re-encrypt with service rotating key
        5. Create PaymentToken entity

        Args:
            restaurant_id: UUID of restaurant/merchant
            encrypted_payment_data_from_device: Payment data encrypted by device
            device_token: Device identifier for key derivation
            bdk: Base Derivation Key from KMS
            service_encryption_key: Current service encryption key
            service_key_version: Version of service encryption key
            metadata_dict: Optional metadata from client (merged with extracted)
            expiration_hours: Hours until token expires (default 24)

        Returns:
            PaymentToken entity ready for persistence

        Raises:
            DecryptionError: If device decryption fails
            EncryptionError: If re-encryption fails
            ValueError: If payment data is invalid
            TokenError: If token creation fails
        """
        logger.info(
            f"Creating token for restaurant {restaurant_id} from device {device_token}"
        )

        try:
            # Step 1: Decrypt device-encrypted data using BDK-derived key
            decrypted_bytes = decrypt_payment_data(
                encrypted_payment_data_from_device, bdk, device_token
            )
            logger.debug("Device decryption successful")

            # Step 2: Parse decrypted bytes into PaymentData domain object
            payment_data = PaymentData.from_bytes(decrypted_bytes)
            logger.debug("Payment data parsed successfully")

            # Step 3: Extract metadata from payment data
            extracted_metadata = TokenMetadata.from_payment_data(payment_data)

            # Merge with client-provided metadata (client metadata takes precedence)
            if metadata_dict:
                metadata = TokenMetadata(
                    card_brand=metadata_dict.get("card_brand")
                    or extracted_metadata.card_brand,
                    last4=metadata_dict.get("last4") or extracted_metadata.last4,
                    exp_month=metadata_dict.get("exp_month")
                    or extracted_metadata.exp_month,
                    exp_year=metadata_dict.get("exp_year")
                    or extracted_metadata.exp_year,
                )
            else:
                metadata = extracted_metadata

            logger.debug(f"Metadata extracted: {metadata.to_dict()}")

            # Step 4: Re-encrypt with service rotating key
            payment_data_bytes = payment_data.to_bytes()
            encrypted_with_service_key = encrypt_with_key(
                payment_data_bytes, service_encryption_key
            )

            # Serialize encrypted data (ciphertext + nonce)
            encrypted_payment_data = self._serialize_encrypted_data(
                encrypted_with_service_key
            )
            logger.debug("Re-encryption with service key successful")

            # Step 5: Create PaymentToken entity
            token = PaymentToken.create(
                restaurant_id=restaurant_id,
                encrypted_payment_data=encrypted_payment_data,
                encryption_key_version=service_key_version,
                device_token=device_token,
                metadata=metadata,
                expiration_hours=expiration_hours,
            )

            logger.info(f"Token created successfully: {token.payment_token}")
            return token

        except DecryptionError as e:
            logger.error(f"Device decryption failed: {str(e)}")
            raise
        except EncryptionError as e:
            logger.error(f"Service encryption failed: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"Payment data validation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating token: {str(e)}")
            raise TokenError(f"Failed to create token: {str(e)}") from e

    def decrypt_token(
        self,
        token: PaymentToken,
        service_encryption_key: bytes,
    ) -> PaymentData:
        """Decrypt a payment token to retrieve payment data.

        Args:
            token: PaymentToken entity to decrypt
            service_encryption_key: Service encryption key for token's key version

        Returns:
            Decrypted PaymentData

        Raises:
            DecryptionError: If decryption fails
            ValueError: If payment data format is invalid
        """
        logger.info(f"Decrypting token {token.payment_token}")

        try:
            # Deserialize encrypted data
            encrypted_data = self._deserialize_encrypted_data(
                token.encrypted_payment_data
            )

            # Decrypt with service key
            decrypted_bytes = decrypt_with_key(encrypted_data, service_encryption_key)
            logger.debug("Service decryption successful")

            # Parse into PaymentData domain object
            payment_data = PaymentData.from_bytes(decrypted_bytes)
            logger.debug("Payment data parsed successfully")

            return payment_data

        except DecryptionError as e:
            logger.error(f"Token decryption failed: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"Payment data parsing failed: {str(e)}")
            raise

    def re_encrypt_token(
        self,
        token: PaymentToken,
        old_service_key: bytes,
        new_service_key: bytes,
        new_key_version: str,
    ) -> PaymentToken:
        """Re-encrypt a token with a new service key (for key rotation).

        This is used during key rotation to migrate tokens from an old
        encryption key to a new one.

        Args:
            token: Existing PaymentToken to re-encrypt
            old_service_key: Current service encryption key
            new_service_key: New service encryption key
            new_key_version: New key version identifier

        Returns:
            Updated PaymentToken with new encrypted data and key version

        Raises:
            DecryptionError: If decryption with old key fails
            EncryptionError: If encryption with new key fails
        """
        logger.info(
            f"Re-encrypting token {token.payment_token} from {token.encryption_key_version} to {new_key_version}"
        )

        try:
            # Decrypt with old key
            payment_data = self.decrypt_token(token, old_service_key)

            # Re-encrypt with new key
            payment_data_bytes = payment_data.to_bytes()
            encrypted_with_new_key = encrypt_with_key(payment_data_bytes, new_service_key)

            # Serialize encrypted data
            new_encrypted_payment_data = self._serialize_encrypted_data(
                encrypted_with_new_key
            )

            # Update token with new encrypted data and key version
            token.encrypted_payment_data = new_encrypted_payment_data
            token.encryption_key_version = new_key_version

            logger.info(
                f"Token {token.payment_token} re-encrypted successfully to {new_key_version}"
            )
            return token

        except (DecryptionError, EncryptionError) as e:
            logger.error(f"Re-encryption failed: {str(e)}")
            raise

    def _serialize_encrypted_data(self, encrypted_data: EncryptedData) -> bytes:
        """Serialize EncryptedData for storage.

        Format: nonce (12 bytes) + ciphertext (variable)

        Args:
            encrypted_data: EncryptedData to serialize

        Returns:
            Serialized bytes suitable for database storage
        """
        return encrypted_data.nonce + encrypted_data.ciphertext

    def _deserialize_encrypted_data(self, data: bytes) -> EncryptedData:
        """Deserialize stored encrypted data.

        Args:
            data: Serialized encrypted data from database

        Returns:
            EncryptedData with nonce and ciphertext

        Raises:
            ValueError: If data format is invalid
        """
        if len(data) < 12:
            raise ValueError("Encrypted data must be at least 12 bytes (nonce)")

        nonce = data[:12]
        ciphertext = data[12:]

        return EncryptedData(ciphertext=ciphertext, nonce=nonce)


def validate_token_for_use(token: PaymentToken, restaurant_id: str) -> None:
    """Validate that a token can be used by a restaurant.

    This enforces business rules B4 (expiration) and B5 (restaurant scoping).

    Args:
        token: PaymentToken to validate
        restaurant_id: Restaurant ID attempting to use token

    Raises:
        TokenExpiredError: If token has expired
        TokenOwnershipError: If restaurant doesn't own token
    """
    token.validate_ownership(restaurant_id)
    token.validate_not_expired()
