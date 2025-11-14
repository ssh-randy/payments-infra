"""SQLAlchemy ORM models for Payment Token Service."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Index,
    BigInteger,
    LargeBinary,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from payment_token.infrastructure.database import Base


class PaymentToken(Base):
    """
    Core table for storing encrypted payment tokens.

    Stores device-encrypted payment data that has been re-encrypted with
    the service's rotating keys for secure storage.
    """

    __tablename__ = "payment_tokens"

    # Primary identifier (format: pt_<uuid>)
    payment_token: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Token ID in format pt_<uuid>"
    )

    # Restaurant/merchant identifier
    restaurant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True, comment="Restaurant UUID"
    )

    # Re-encrypted payment data (encrypted with service rotating key)
    encrypted_payment_data: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, comment="Payment data encrypted with service key"
    )

    # Encryption key version for rotation support
    encryption_key_version: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Version of encryption key used"
    )

    # Key ID used for encryption (API partner keys)
    encryption_key_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment='Key ID used for encryption (e.g., "primary", "ak_{uuid}", "bdk_{id}")'
    )

    # Original device token (for audit purposes, nullable for API partner key flow)
    device_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Device identifier used for original encryption (null for API partner keys)"
    )

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Token creation timestamp",
    )

    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="Token expiration timestamp"
    )

    # Non-sensitive metadata (card brand, last 4 digits, etc.)
    # Note: Using 'token_metadata' to avoid conflict with SQLAlchemy's reserved 'metadata'
    token_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True, comment="Non-sensitive metadata (card_brand, last4, etc.)"
    )

    # Indexes for query performance
    __table_args__ = (
        Index("idx_restaurant_created", "restaurant_id", "created_at"),
        Index("idx_expires_at", "expires_at"),
    )

    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.utcnow() > self.expires_at


class TokenIdempotencyKey(Base):
    """
    Idempotency key tracking for token creation.

    Ensures that duplicate requests with the same idempotency key
    return the same token within a 24-hour window.
    """

    __tablename__ = "token_idempotency_keys"

    # Composite primary key: idempotency_key + restaurant_id
    idempotency_key: Mapped[str] = mapped_column(
        String(255), primary_key=True, comment="Client-provided idempotency key"
    )

    restaurant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, comment="Restaurant UUID"
    )

    # Reference to the created token
    payment_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Payment token created for this idempotency key",
    )

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Idempotency key creation timestamp",
    )

    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="Idempotency key expiration (24 hours)",
    )

    # Index for cleanup of expired keys
    __table_args__ = (Index("idx_idempotency_expires_at", "expires_at"),)


class EncryptionKey(Base):
    """
    Encryption key version tracking for rotation support.

    Stores metadata about service encryption keys (not the keys themselves,
    which are stored in AWS KMS). Supports multiple key versions during rotation.
    """

    __tablename__ = "encryption_keys"

    # Key version identifier (e.g., "v1", "v2", "v3")
    key_version: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="Encryption key version identifier"
    )

    # AWS KMS key ARN
    kms_key_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="AWS KMS key ARN"
    )

    # Lifecycle
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Key version creation timestamp",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether this key is currently active"
    )

    retired_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="When this key was retired"
    )

    # Constraint: only one active key at a time
    # Note: This is enforced at the application level rather than database level
    # because CHECK constraints with subqueries are complex in PostgreSQL


class DecryptAuditLog(Base):
    """
    Audit log for all decryption requests (PCI compliance).

    Immutable log of all decrypt operations, retained for 7 years per PCI requirements.
    Partitioned by month for efficient archival.
    """

    __tablename__ = "decrypt_audit_log"

    # Auto-incrementing primary key
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Audit log entry ID"
    )

    # Request details
    payment_token: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="Token that was decrypted"
    )

    restaurant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, comment="Restaurant UUID"
    )

    requesting_service: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Service that requested decryption (e.g., auth-processor-worker)",
    )

    request_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Correlation/request ID for tracing"
    )

    # Outcome
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="Whether decryption succeeded"
    )

    error_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Error code if decryption failed"
    )

    # Timestamp (used for partitioning)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Audit log entry creation timestamp",
    )

    # Composite index for token-based queries
    __table_args__ = (
        Index("idx_token_created", "payment_token", "created_at"),
        # Note: Table partitioning by month would be defined in the Alembic migration
    )
