"""FastAPI routes for Payment Token Service.

This module implements the REST API endpoints for payment token operations:
- POST /v1/payment-tokens: Create payment token from device-encrypted data
- GET /v1/payment-tokens/{token_id}: Retrieve token metadata
- POST /internal/v1/decrypt: Decrypt token (internal API only)
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import Response as FastAPIResponse

from payment_token.api.dependencies import (
    APIKey,
    IdempotencyKey,
    KMS,
    ServiceKey,
    TokenRepo,
    TokenSvc,
)
from payment_token.config import settings
from payment_token.domain.encryption import DecryptionError, EncryptedData, EncryptionError
from payment_token.domain.token import TokenError, TokenExpiredError, TokenOwnershipError
from payment_token.infrastructure.kms import KMSError

# Import generated protobuf messages
from payments_proto.payments.v1 import payment_token_pb2

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter()


@router.post(
    "/v1/payment-tokens",
    status_code=status.HTTP_201_CREATED,
    response_class=FastAPIResponse,
)
async def create_payment_token(
    request: Request,
    api_key: APIKey,
    idempotency_key: IdempotencyKey,
    kms_client: KMS,
    service_key: ServiceKey,
    token_repo: TokenRepo,
    token_service: TokenSvc,
) -> Response:
    """Create a payment token from device-encrypted payment data.

    This endpoint implements the complete token creation flow:
    1. Check idempotency key (return existing token if found)
    2. Parse protobuf request
    3. Retrieve BDK from KMS
    4. Decrypt device-encrypted data using device-derived key
    5. Re-encrypt with service rotating key
    6. Generate and store token
    7. Return protobuf response

    Args:
        request: FastAPI request object (for reading body)
        api_key: Validated API key from Authorization header
        idempotency_key: Optional idempotency key from X-Idempotency-Key header
        kms_client: KMS client for BDK retrieval
        service_key: Current service encryption key
        token_repo: Token repository for database operations
        token_service: Token domain service for business logic

    Returns:
        Protobuf-encoded CreatePaymentTokenResponse

    Responses:
        201 Created: Token created successfully
        200 OK: Idempotent request, returning existing token
        400 Bad Request: Invalid request or decryption failed
        401 Unauthorized: Invalid API key
        500 Internal Server Error: System error
    """
    logger.info("Received create payment token request")

    try:
        # Read raw protobuf request body
        body = await request.body()
        if not body:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty request body",
            )

        # Parse protobuf request
        try:
            pb_request = payment_token_pb2.CreatePaymentTokenRequest()
            pb_request.ParseFromString(body)
        except Exception as e:
            logger.error(f"Failed to parse protobuf request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid protobuf request: {str(e)}",
            )

        # Validate required fields
        if not pb_request.restaurant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="restaurant_id is required",
            )
        if not pb_request.encrypted_payment_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="encrypted_payment_data is required",
            )
        if not pb_request.device_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="device_token is required",
            )

        logger.info(
            f"Processing token creation for restaurant {pb_request.restaurant_id}, "
            f"device {pb_request.device_token[:8]}..."
        )

        # Check idempotency key (B1: Idempotency)
        is_idempotent = False
        if idempotency_key:
            logger.debug(f"Checking idempotency key: {idempotency_key}")
            existing_token_id = token_repo.get_token_by_idempotency_key(
                idempotency_key, pb_request.restaurant_id
            )

            if existing_token_id:
                logger.info(
                    f"Idempotent request: returning existing token {existing_token_id}"
                )
                existing_token = token_repo.get_token(existing_token_id)

                if not existing_token:
                    # This shouldn't happen, but handle gracefully
                    logger.error(
                        f"Token {existing_token_id} referenced by idempotency key not found"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Internal error retrieving existing token",
                    )

                # Return existing token with 200 OK
                pb_response = payment_token_pb2.CreatePaymentTokenResponse(
                    payment_token=existing_token.payment_token,
                    restaurant_id=existing_token.restaurant_id,
                    expires_at=int(existing_token.expires_at.timestamp()),
                    metadata=(
                        existing_token.metadata.to_dict()
                        if existing_token.metadata
                        else {}
                    ),
                )

                return Response(
                    content=pb_response.SerializeToString(),
                    media_type="application/x-protobuf",
                    status_code=status.HTTP_200_OK,
                )

        # Retrieve BDK from KMS (B2: Device-based decryption)
        try:
            logger.debug("Retrieving BDK from KMS")
            bdk = kms_client.get_bdk(
                encryption_context={
                    "service": "payment-token",
                    "purpose": "device-key-derivation",
                }
            )
        except KMSError as e:
            logger.error(f"Failed to retrieve BDK from KMS: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption service unavailable",
            )

        # Deserialize encrypted data from device (format: nonce + ciphertext)
        # Device encryption includes 12-byte nonce followed by ciphertext
        device_data = pb_request.encrypted_payment_data
        if len(device_data) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid encrypted payment data: too short",
            )

        encrypted_data_from_device = EncryptedData(
            nonce=device_data[:12],  # First 12 bytes are nonce
            ciphertext=device_data[12:],  # Rest is ciphertext
        )

        # Create token using domain service (B2 + B3)
        try:
            token = token_service.create_token_from_device_encrypted_data(
                restaurant_id=pb_request.restaurant_id,
                encrypted_payment_data_from_device=encrypted_data_from_device,
                device_token=pb_request.device_token,
                bdk=bdk,
                service_encryption_key=service_key,
                service_key_version=settings.current_key_version,
                metadata_dict=dict(pb_request.metadata) if pb_request.metadata else None,
                expiration_hours=settings.default_token_ttl_hours,
            )
        except DecryptionError as e:
            logger.warning(f"Device decryption failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to decrypt payment data. Invalid device_token or corrupted data.",
            )
        except (EncryptionError, ValueError, TokenError) as e:
            logger.error(f"Token creation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create token: {str(e)}",
            )

        # Save token to database
        try:
            token_repo.save_token(token)
            logger.info(f"Token {token.payment_token} saved to database")

            # Save idempotency key mapping if provided
            if idempotency_key:
                token_repo.save_idempotency_key(
                    idempotency_key=idempotency_key,
                    restaurant_id=pb_request.restaurant_id,
                    payment_token=token.payment_token,
                    expires_hours=24,
                )
                logger.debug(f"Idempotency key {idempotency_key} saved")

        except Exception as e:
            logger.error(f"Failed to save token to database: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store token",
            )

        # Build protobuf response
        pb_response = payment_token_pb2.CreatePaymentTokenResponse(
            payment_token=token.payment_token,
            restaurant_id=token.restaurant_id,
            expires_at=int(token.expires_at.timestamp()),
            metadata=token.metadata.to_dict() if token.metadata else {},
        )

        logger.info(
            f"Token {token.payment_token} created successfully for restaurant {pb_request.restaurant_id}"
        )

        # Return protobuf response
        return Response(
            content=pb_response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=status.HTTP_201_CREATED,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.exception(f"Unexpected error creating token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get(
    "/v1/payment-tokens/{token_id}",
    response_class=FastAPIResponse,
)
async def get_payment_token(
    token_id: str,
    restaurant_id: str,
    api_key: APIKey,
    token_repo: TokenRepo,
) -> Response:
    """Retrieve payment token metadata (NOT the actual payment data).

    Args:
        token_id: Payment token ID to retrieve
        restaurant_id: Restaurant ID (must match token owner)
        api_key: Validated API key from Authorization header
        token_repo: Token repository for database operations

    Returns:
        Protobuf-encoded GetPaymentTokenResponse

    Responses:
        200 OK: Token found
        404 Not Found: Token doesn't exist or doesn't belong to restaurant
        410 Gone: Token expired
        401 Unauthorized: Invalid API key
    """
    logger.info(f"Received get payment token request for {token_id}")

    try:
        # Retrieve token with restaurant ownership check (B5)
        token = token_repo.get_token_by_restaurant(token_id, restaurant_id)

        if not token:
            logger.warning(f"Token {token_id} not found for restaurant {restaurant_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        # Check if token is expired (B4)
        if token.is_expired():
            logger.warning(f"Token {token_id} has expired")
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token has expired",
            )

        # Build protobuf response
        pb_response = payment_token_pb2.GetPaymentTokenResponse(
            payment_token=token.payment_token,
            restaurant_id=token.restaurant_id,
            created_at=int(token.created_at.timestamp()),
            expires_at=int(token.expires_at.timestamp()),
            is_expired=token.is_expired(),
            metadata=token.metadata.to_dict() if token.metadata else {},
        )

        logger.info(f"Token {token_id} retrieved successfully")

        return Response(
            content=pb_response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=status.HTTP_200_OK,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error retrieving token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
