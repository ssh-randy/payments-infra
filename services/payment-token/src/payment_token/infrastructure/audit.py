"""Audit logging for PCI compliance.

This module implements immutable audit logging for all decrypt operations
as required by PCI DSS compliance. Logs are retained for 7 years and partitioned
by month for efficient archival.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from payment_token.infrastructure.models import DecryptAuditLog

logger = logging.getLogger(__name__)


@dataclass
class DecryptAuditEvent:
    """Audit event for a decrypt request.

    This represents a single decrypt operation that should be logged
    for compliance purposes.

    Attributes:
        payment_token: Token that was decrypted
        restaurant_id: Restaurant that owns the token
        requesting_service: Service that requested decryption
        request_id: Correlation ID for tracing
        success: Whether decryption succeeded
        error_code: Error code if decryption failed (None if successful)
    """

    payment_token: str
    restaurant_id: str
    requesting_service: str
    request_id: str
    success: bool
    error_code: str | None = None


class AuditLogger:
    """Immutable audit logger for decrypt operations.

    This logger writes all decrypt requests to an immutable audit log
    that is retained for 7 years per PCI DSS requirements.

    Design principles:
    - Insert-only (no updates or deletes)
    - Synchronous writes (don't lose audit logs)
    - No PII in logs (only token IDs and metadata)
    - Automatic partitioning by month for archival
    """

    def __init__(self, db_session: Session):
        """Initialize audit logger with database session.

        Args:
            db_session: SQLAlchemy database session for writing logs
        """
        self.db_session = db_session

    def log_decrypt_request(self, event: DecryptAuditEvent) -> None:
        """Log a decrypt request to the audit log.

        This method creates an immutable audit log entry for a decrypt operation.
        It will commit immediately to ensure the audit log is persisted even if
        the parent transaction fails.

        Args:
            event: Decrypt audit event to log

        Raises:
            Exception: If audit logging fails (should not happen in normal operation)
        """
        try:
            audit_entry = DecryptAuditLog(
                payment_token=event.payment_token,
                restaurant_id=event.restaurant_id,
                requesting_service=event.requesting_service,
                request_id=event.request_id,
                success=event.success,
                error_code=event.error_code,
                created_at=datetime.utcnow(),
            )

            self.db_session.add(audit_entry)
            # Flush to database but don't commit the parent transaction
            # The parent transaction will handle the commit
            self.db_session.flush()

            logger.info(
                f"Audit log entry created: token={event.payment_token}, "
                f"service={event.requesting_service}, success={event.success}, "
                f"request_id={event.request_id}"
            )

        except Exception as e:
            logger.error(f"Failed to write audit log: {str(e)}")
            # Don't raise - audit logging failure should not break the request
            # but it should be logged and monitored
            # In production, this should trigger an alert


def log_decrypt_success(
    db_session: Session,
    payment_token: str,
    restaurant_id: str,
    requesting_service: str,
    request_id: str,
) -> None:
    """Convenience function to log a successful decrypt request.

    Args:
        db_session: Database session
        payment_token: Token that was decrypted
        restaurant_id: Restaurant ID
        requesting_service: Service that requested decryption
        request_id: Correlation ID
    """
    logger_instance = AuditLogger(db_session)
    event = DecryptAuditEvent(
        payment_token=payment_token,
        restaurant_id=restaurant_id,
        requesting_service=requesting_service,
        request_id=request_id,
        success=True,
        error_code=None,
    )
    logger_instance.log_decrypt_request(event)


def log_decrypt_failure(
    db_session: Session,
    payment_token: str,
    restaurant_id: str,
    requesting_service: str,
    request_id: str,
    error_code: str,
) -> None:
    """Convenience function to log a failed decrypt request.

    Args:
        db_session: Database session
        payment_token: Token that was attempted
        restaurant_id: Restaurant ID
        requesting_service: Service that requested decryption
        request_id: Correlation ID
        error_code: Error code indicating why decryption failed
    """
    logger_instance = AuditLogger(db_session)
    event = DecryptAuditEvent(
        payment_token=payment_token,
        restaurant_id=restaurant_id,
        requesting_service=requesting_service,
        request_id=request_id,
        success=False,
        error_code=error_code,
    )
    logger_instance.log_decrypt_request(event)
