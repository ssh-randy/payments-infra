"""FastAPI dependencies for authentication, validation, and dependency injection.

This module provides reusable dependencies for the API routes including:
- Database session management
- Authentication/authorization
- KMS client injection
- Service layer injection
"""

import logging
from typing import Annotated, Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from payment_token.config import settings
from payment_token.domain.services import TokenService
from payment_token.infrastructure.database import get_db_session
from payment_token.infrastructure.kms import KMSClient
from payment_token.infrastructure.repository import TokenRepository, EncryptionKeyRepository

logger = logging.getLogger(__name__)


# Database session dependency
def get_db() -> Generator[Session, None, None]:
    """Provide database session for request.

    Yields:
        SQLAlchemy session that is automatically committed/rolled back
    """
    with get_db_session() as session:
        yield session


# Type alias for database session dependency
DBSession = Annotated[Session, Depends(get_db)]


# Authentication dependency
async def verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify API key from Authorization header.

    Args:
        authorization: Authorization header value (Bearer <token>)

    Returns:
        Validated API key

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not authorization:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = parts[1]

    # TODO: Implement actual API key validation
    # For now, accept any non-empty key
    # In production, validate against database or API key service
    if not api_key or len(api_key) < 10:
        logger.warning("Invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(f"API key validated: {api_key[:8]}...")
    return api_key


# Type alias for API key dependency
APIKey = Annotated[str, Depends(verify_api_key)]


# Idempotency key dependency
async def get_idempotency_key(
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> str | None:
    """Extract idempotency key from request header.

    Args:
        x_idempotency_key: X-Idempotency-Key header value

    Returns:
        Idempotency key if provided, None otherwise

    Note:
        Idempotency key is optional but recommended for idempotent operations.
    """
    if x_idempotency_key:
        logger.debug(f"Idempotency key: {x_idempotency_key}")
    return x_idempotency_key


# Type alias for idempotency key dependency
IdempotencyKey = Annotated[str | None, Depends(get_idempotency_key)]


# KMS client dependency
def get_kms_client() -> KMSClient:
    """Provide KMS client for encryption operations.

    Returns:
        Configured KMS client

    Raises:
        HTTPException: 500 if KMS configuration is invalid
    """
    if not settings.bdk_kms_key_id:
        logger.error("BDK KMS key ID not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption service not configured",
        )

    return KMSClient(
        bdk_kms_key_id=settings.bdk_kms_key_id,
        region=settings.aws_region,
        endpoint_url=settings.kms_endpoint_url,
    )


# Type alias for KMS client dependency
KMS = Annotated[KMSClient, Depends(get_kms_client)]


# Token repository dependency
def get_token_repository(session: DBSession) -> TokenRepository:
    """Provide token repository for database operations.

    Args:
        session: Database session

    Returns:
        TokenRepository instance
    """
    return TokenRepository(session)


# Type alias for token repository dependency
TokenRepo = Annotated[TokenRepository, Depends(get_token_repository)]


# Encryption key repository dependency
def get_encryption_key_repository(session: DBSession) -> EncryptionKeyRepository:
    """Provide encryption key repository for key version management.

    Args:
        session: Database session

    Returns:
        EncryptionKeyRepository instance
    """
    return EncryptionKeyRepository(session)


# Type alias for encryption key repository dependency
EncryptionKeyRepo = Annotated[EncryptionKeyRepository, Depends(get_encryption_key_repository)]


# Token service dependency
def get_token_service() -> TokenService:
    """Provide token domain service.

    Returns:
        TokenService instance
    """
    return TokenService()


# Type alias for token service dependency
TokenSvc = Annotated[TokenService, Depends(get_token_service)]


# Service encryption key dependency
def get_service_encryption_key() -> bytes:
    """Get current service encryption key for token re-encryption.

    Returns:
        Service encryption key bytes

    Note:
        In production, this should retrieve the actual key from KMS.
        For now, returns a deterministic test key.
    """
    # TODO: Implement actual key retrieval from KMS based on current_key_version
    # For testing, use a deterministic key
    import hashlib

    key_version = settings.current_key_version
    deterministic_key = hashlib.sha256(f"service-key-{key_version}".encode()).digest()

    return deterministic_key


# Type alias for service encryption key dependency
ServiceKey = Annotated[bytes, Depends(get_service_encryption_key)]
