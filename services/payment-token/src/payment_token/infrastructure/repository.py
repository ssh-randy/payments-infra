"""Repository layer for payment token database operations.

This module provides the data access layer for payment tokens,
handling all database CRUD operations and idempotency tracking.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from payment_token.infrastructure.models import (
    PaymentToken as PaymentTokenModel,
    TokenIdempotencyKey,
    EncryptionKey as EncryptionKeyModel,
)
from payment_token.domain.token import PaymentToken, TokenMetadata

logger = logging.getLogger(__name__)


class TokenRepository:
    """Repository for payment token database operations.

    Handles storage, retrieval, and idempotency management for payment tokens.
    """

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def save_token(self, token: PaymentToken) -> None:
        """Save a payment token to the database.

        Args:
            token: PaymentToken domain entity to persist

        Raises:
            IntegrityError: If token_id already exists (duplicate)
        """
        logger.info(f"Saving token {token.payment_token} to database")

        # Convert domain entity to ORM model
        token_model = PaymentTokenModel(
            payment_token=token.payment_token,
            restaurant_id=token.restaurant_id,
            encrypted_payment_data=token.encrypted_payment_data,
            encryption_key_version=token.encryption_key_version,
            device_token=token.device_token,
            created_at=token.created_at,
            expires_at=token.expires_at,
            token_metadata=token.metadata.to_dict() if token.metadata else None,
        )

        self.session.add(token_model)
        self.session.flush()  # Flush to check for integrity errors

        logger.debug(f"Token {token.payment_token} saved successfully")

    def get_token(self, payment_token: str) -> Optional[PaymentToken]:
        """Retrieve a payment token by ID.

        Args:
            payment_token: Token ID to retrieve

        Returns:
            PaymentToken domain entity if found, None otherwise
        """
        logger.debug(f"Retrieving token {payment_token}")

        token_model = (
            self.session.query(PaymentTokenModel)
            .filter(PaymentTokenModel.payment_token == payment_token)
            .first()
        )

        if not token_model:
            logger.debug(f"Token {payment_token} not found")
            return None

        # Convert ORM model to domain entity
        return self._to_domain_entity(token_model)

    def get_token_by_restaurant(
        self, payment_token: str, restaurant_id: str
    ) -> Optional[PaymentToken]:
        """Retrieve a payment token with restaurant ownership verification.

        Args:
            payment_token: Token ID to retrieve
            restaurant_id: Restaurant ID that must own the token

        Returns:
            PaymentToken domain entity if found and owned by restaurant, None otherwise
        """
        logger.debug(f"Retrieving token {payment_token} for restaurant {restaurant_id}")

        token_model = (
            self.session.query(PaymentTokenModel)
            .filter(
                PaymentTokenModel.payment_token == payment_token,
                PaymentTokenModel.restaurant_id == restaurant_id,
            )
            .first()
        )

        if not token_model:
            logger.debug(f"Token {payment_token} not found for restaurant {restaurant_id}")
            return None

        return self._to_domain_entity(token_model)

    def save_idempotency_key(
        self,
        idempotency_key: str,
        restaurant_id: str,
        payment_token: str,
        expires_hours: int = 24,
    ) -> None:
        """Save an idempotency key mapping.

        Args:
            idempotency_key: Client-provided idempotency key
            restaurant_id: Restaurant ID
            payment_token: Token ID created for this idempotency key
            expires_hours: Hours until idempotency key expires (default 24)

        Raises:
            IntegrityError: If idempotency key already exists for this restaurant
        """
        logger.debug(f"Saving idempotency key {idempotency_key} for restaurant {restaurant_id}")

        idempotency_model = TokenIdempotencyKey(
            idempotency_key=idempotency_key,
            restaurant_id=restaurant_id,
            payment_token=payment_token,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
        )

        self.session.add(idempotency_model)
        self.session.flush()

        logger.debug(f"Idempotency key {idempotency_key} saved successfully")

    def get_token_by_idempotency_key(
        self, idempotency_key: str, restaurant_id: str
    ) -> Optional[str]:
        """Get payment token ID for an idempotency key if it exists and is not expired.

        Args:
            idempotency_key: Client-provided idempotency key
            restaurant_id: Restaurant ID

        Returns:
            Payment token ID if found and not expired, None otherwise
        """
        logger.debug(
            f"Checking idempotency key {idempotency_key} for restaurant {restaurant_id}"
        )

        idempotency_model = (
            self.session.query(TokenIdempotencyKey)
            .filter(
                TokenIdempotencyKey.idempotency_key == idempotency_key,
                TokenIdempotencyKey.restaurant_id == restaurant_id,
                TokenIdempotencyKey.expires_at > datetime.utcnow(),
            )
            .first()
        )

        if not idempotency_model:
            logger.debug(f"No valid idempotency key found")
            return None

        logger.debug(f"Found existing token {idempotency_model.payment_token} for idempotency key")
        return idempotency_model.payment_token

    def update_token(self, token: PaymentToken) -> None:
        """Update an existing token (e.g., for key rotation).

        Args:
            token: PaymentToken domain entity with updated values

        Raises:
            ValueError: If token doesn't exist
        """
        logger.info(f"Updating token {token.payment_token}")

        token_model = (
            self.session.query(PaymentTokenModel)
            .filter(PaymentTokenModel.payment_token == token.payment_token)
            .first()
        )

        if not token_model:
            raise ValueError(f"Token {token.payment_token} not found")

        # Update mutable fields
        token_model.encrypted_payment_data = token.encrypted_payment_data
        token_model.encryption_key_version = token.encryption_key_version
        token_model.token_metadata = token.metadata.to_dict() if token.metadata else None

        self.session.flush()
        logger.debug(f"Token {token.payment_token} updated successfully")

    def _to_domain_entity(self, model: PaymentTokenModel) -> PaymentToken:
        """Convert ORM model to domain entity.

        Args:
            model: SQLAlchemy ORM model

        Returns:
            PaymentToken domain entity
        """
        metadata = None
        if model.token_metadata:
            metadata = TokenMetadata.from_dict(model.token_metadata)

        return PaymentToken(
            payment_token=model.payment_token,
            restaurant_id=model.restaurant_id,
            encrypted_payment_data=model.encrypted_payment_data,
            encryption_key_version=model.encryption_key_version,
            device_token=model.device_token,
            created_at=model.created_at,
            expires_at=model.expires_at,
            metadata=metadata,
        )


class EncryptionKeyRepository:
    """Repository for encryption key version management."""

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def get_active_key_version(self) -> Optional[str]:
        """Get the currently active encryption key version.

        Returns:
            Active key version string, or None if no active key
        """
        key_model = (
            self.session.query(EncryptionKeyModel)
            .filter(EncryptionKeyModel.is_active == True)
            .first()
        )

        if not key_model:
            return None

        return key_model.key_version

    def get_key_by_version(self, key_version: str) -> Optional[EncryptionKeyModel]:
        """Get encryption key metadata by version.

        Args:
            key_version: Key version identifier

        Returns:
            EncryptionKey model if found, None otherwise
        """
        return (
            self.session.query(EncryptionKeyModel)
            .filter(EncryptionKeyModel.key_version == key_version)
            .first()
        )

    def save_key_version(
        self, key_version: str, kms_key_id: str, is_active: bool = False
    ) -> None:
        """Save a new encryption key version.

        Args:
            key_version: Key version identifier
            kms_key_id: AWS KMS key ARN/ID
            is_active: Whether this is the active key

        Raises:
            IntegrityError: If key_version already exists
        """
        key_model = EncryptionKeyModel(
            key_version=key_version,
            kms_key_id=kms_key_id,
            created_at=datetime.utcnow(),
            is_active=is_active,
        )

        self.session.add(key_model)
        self.session.flush()
