"""Service authentication for internal API endpoints.

This module implements service-level authentication for the internal decrypt API.
Only authorized services (auth-processor-worker, void-processor-worker) can
access the internal endpoints.
"""

import logging
from typing import Annotated

from fastapi import Header, HTTPException, status

from payment_token.config import settings

logger = logging.getLogger(__name__)


class UnauthorizedServiceError(Exception):
    """Exception raised when a service is not authorized to access an endpoint."""

    pass


def verify_service_authorization(
    x_service_auth: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
) -> tuple[str, str]:
    """Verify that the requesting service is authorized.

    This dependency validates the X-Service-Auth header to ensure only
    authorized services can access internal endpoints.

    In production, this should verify mutual TLS certificates instead of
    or in addition to the header-based authentication.

    Args:
        x_service_auth: Service authentication token from X-Service-Auth header
        x_request_id: Request/correlation ID from X-Request-ID header

    Returns:
        Tuple of (requesting_service, request_id)

    Raises:
        HTTPException: If service is not authorized (403)
        HTTPException: If authentication header is missing (401)
    """
    # Validate X-Request-ID header (required for audit logging)
    if not x_request_id:
        logger.warning("Missing X-Request-ID header in internal API request")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Request-ID header is required",
        )

    # Validate X-Service-Auth header
    if not x_service_auth:
        logger.warning(
            f"Missing X-Service-Auth header in internal API request (request_id={x_request_id})"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Service-Auth header is required",
        )

    # Parse service name from auth token
    # In production, this would verify a JWT or mutual TLS certificate
    # For now, we use a simple format: "service:<service-name>"
    if not x_service_auth.startswith("service:"):
        logger.warning(
            f"Invalid X-Service-Auth header format (request_id={x_request_id}): {x_service_auth}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
        )

    requesting_service = x_service_auth.replace("service:", "", 1)

    # Check if service is in allowlist
    if requesting_service not in settings.allowed_services:
        logger.warning(
            f"Unauthorized service attempted to access internal API: {requesting_service} "
            f"(request_id={x_request_id})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Service '{requesting_service}' is not authorized to access this endpoint",
        )

    logger.info(
        f"Service authenticated: {requesting_service} (request_id={x_request_id})"
    )

    return requesting_service, x_request_id


# Type alias for dependency injection
ServiceAuth = Annotated[tuple[str, str], Header()]
