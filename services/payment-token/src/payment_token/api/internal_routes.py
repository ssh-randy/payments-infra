"""Internal API routes for payment token service.

These endpoints are only accessible by authorized services within the VPC
(auth-processor-worker, void-processor-worker) and require service authentication.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from payment_token.api.auth import verify_service_authorization
from payment_token.config import settings
from payment_token.domain.services import TokenService, validate_token_for_use
from payment_token.domain.token import (
    PaymentToken as PaymentTokenDomain,
    TokenExpiredError,
    TokenOwnershipError,
)
from payment_token.infrastructure.audit import log_decrypt_failure, log_decrypt_success
from payment_token.infrastructure.database import get_db
from payment_token.infrastructure.kms import KMSClient
from payment_token.infrastructure.models import PaymentToken as PaymentTokenModel

# Import generated protobuf messages
from payments_proto.payments.v1 import payment_token_pb2

logger = logging.getLogger(__name__)

# Create router for internal API endpoints
router = APIRouter(prefix="/internal/v1", tags=["internal"])


def get_kms_client() -> KMSClient:
    """Get or create KMS client instance (lazy initialization)."""
    return KMSClient(
        bdk_kms_key_id=settings.bdk_kms_key_id or "arn:aws:kms:us-east-1:000000000000:key/test",
        region=settings.aws_region,
        endpoint_url=settings.kms_endpoint_url,
    )


@router.post("/decrypt")
async def decrypt_payment_token(
    request: Request,
    auth_info: Annotated[tuple[str, str], Depends(verify_service_authorization)],
    db: Session = Depends(get_db),
):
    """Decrypt a payment token and return raw payment data.

    This endpoint is for internal use only by authorized services.
    It validates authorization, decrypts the token, and returns the
    full payment data.

    Security:
    - Only accessible by services in the allowlist
    - Requires X-Service-Auth header
    - Requires X-Request-ID header for audit trail
    - All requests are logged to audit table

    Args:
        request_data: Protobuf-encoded DecryptPaymentTokenRequest
        auth_info: Service authentication info (from dependency)
        db: Database session (from dependency)

    Returns:
        Protobuf-encoded DecryptPaymentTokenResponse with decrypted payment data

    Raises:
        HTTPException 400: Invalid request format
        HTTPException 403: Restaurant ID mismatch or unauthorized service
        HTTPException 404: Token not found
        HTTPException 410: Token expired
        HTTPException 500: Internal server error
    """
    requesting_service, request_id = auth_info

    # Note: protobuf messages imported at module level

    # Read raw request body
    request_data = await request.body()

    # Parse protobuf request
    try:
        pb_request = payment_token_pb2.DecryptPaymentTokenRequest()
        pb_request.ParseFromString(request_data)
    except Exception as e:
        logger.error(f"Failed to parse protobuf request: {str(e)}")
        # Log failure to audit log (if we have enough info)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request format",
        )

    payment_token_id = pb_request.payment_token
    restaurant_id = pb_request.restaurant_id

    logger.info(
        f"Decrypt request: token={payment_token_id}, restaurant={restaurant_id}, "
        f"service={requesting_service}, request_id={request_id}"
    )

    try:
        # Step 1: Retrieve token from database
        token_model = (
            db.query(PaymentTokenModel)
            .filter(PaymentTokenModel.payment_token == payment_token_id)
            .first()
        )

        if not token_model:
            logger.warning(
                f"Token not found: {payment_token_id} (request_id={request_id})"
            )
            log_decrypt_failure(
                db,
                payment_token_id,
                restaurant_id,
                requesting_service,
                request_id,
                "token_not_found",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        # Step 2: Convert to domain model
        token_domain = PaymentTokenDomain(
            payment_token=token_model.payment_token,
            restaurant_id=token_model.restaurant_id,
            encrypted_payment_data=token_model.encrypted_payment_data,
            encryption_key_version=token_model.encryption_key_version,
            device_token=token_model.device_token,
            encryption_key_id=token_model.encryption_key_id,
            created_at=token_model.created_at,
            expires_at=token_model.expires_at,
        )

        # Step 3: Validate ownership and expiration
        try:
            validate_token_for_use(token_domain, restaurant_id)
        except TokenOwnershipError as e:
            logger.warning(
                f"Token ownership validation failed: {str(e)} (request_id={request_id})"
            )
            log_decrypt_failure(
                db,
                payment_token_id,
                restaurant_id,
                requesting_service,
                request_id,
                "restaurant_mismatch",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Restaurant ID mismatch",
            )
        except TokenExpiredError as e:
            logger.warning(
                f"Token expired: {str(e)} (request_id={request_id})"
            )
            log_decrypt_failure(
                db,
                payment_token_id,
                restaurant_id,
                requesting_service,
                request_id,
                "token_expired",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token expired",
            )

        # Step 4: Get encryption key for token's key version
        # For now, we assume all tokens use the current key version
        # In production, this would lookup the key based on encryption_key_version
        kms = get_kms_client()
        service_key = kms.get_service_encryption_key(token_model.encryption_key_version)

        # Step 5: Decrypt token
        token_service = TokenService()
        payment_data = token_service.decrypt_token(token_domain, service_key)

        # Step 6: Log successful decrypt to audit log
        log_decrypt_success(
            db,
            payment_token_id,
            restaurant_id,
            requesting_service,
            request_id,
        )
        db.commit()

        # Step 7: Build protobuf response
        response = payment_token_pb2.DecryptPaymentTokenResponse()
        response.payment_data.card_number = payment_data.card_number
        response.payment_data.exp_month = payment_data.exp_month
        response.payment_data.exp_year = payment_data.exp_year
        response.payment_data.cvv = payment_data.cvv
        response.payment_data.cardholder_name = payment_data.cardholder_name

        # Add billing address if present
        if payment_data.billing_address:
            response.payment_data.billing_address.line1 = payment_data.billing_address.get("line1", "")
            response.payment_data.billing_address.line2 = payment_data.billing_address.get("line2", "")
            response.payment_data.billing_address.city = payment_data.billing_address.get("city", "")
            response.payment_data.billing_address.state = payment_data.billing_address.get("state", "")
            response.payment_data.billing_address.postal_code = payment_data.billing_address.get("postal_code", "")
            response.payment_data.billing_address.country = payment_data.billing_address.get("country", "")

        # Add metadata if present
        if token_model.token_metadata:
            for key, value in token_model.token_metadata.items():
                response.metadata[key] = str(value)

        logger.info(
            f"Decrypt successful: token={payment_token_id} (request_id={request_id})"
        )

        # Return protobuf response
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error decrypting token: {str(e)} (request_id={request_id})",
            exc_info=True,
        )
        # Log failure to audit log
        try:
            log_decrypt_failure(
                db,
                payment_token_id,
                restaurant_id,
                requesting_service,
                request_id,
                "internal_error",
            )
            db.commit()
        except Exception as audit_error:
            logger.error(f"Failed to log audit failure: {str(audit_error)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
