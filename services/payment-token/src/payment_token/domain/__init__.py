"""Payment token domain layer.

This package contains the core domain entities, value objects, services,
and interfaces for the payment token bounded context.
"""

from payment_token.domain.encryption import (
    DecryptionError,
    EncryptedData,
    EncryptionError,
    EncryptionMetadata,
    decrypt_payment_data,
    decrypt_with_encryption_metadata,
    decrypt_with_key,
    encrypt_with_key,
)
from payment_token.domain.identity_token import ICardIdentityTokenRepository
from payment_token.domain.services import TokenService, validate_token_for_use
from payment_token.domain.token import (
    PaymentData,
    PaymentToken,
    TokenError,
    TokenExpiredError,
    TokenMetadata,
    TokenOwnershipError,
)

__all__ = [
    # Token models
    "PaymentToken",
    "PaymentData",
    "TokenMetadata",
    # Token exceptions
    "TokenError",
    "TokenExpiredError",
    "TokenOwnershipError",
    # Encryption
    "EncryptedData",
    "EncryptionMetadata",
    "EncryptionError",
    "DecryptionError",
    "encrypt_with_key",
    "decrypt_with_key",
    "decrypt_payment_data",
    "decrypt_with_encryption_metadata",
    # Services
    "TokenService",
    "validate_token_for_use",
    # Repository interfaces
    "ICardIdentityTokenRepository",
]
