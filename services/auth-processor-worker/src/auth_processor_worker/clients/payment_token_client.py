"""Payment Token Service client for decrypting payment tokens."""

import sys
import uuid
from pathlib import Path

import httpx
import structlog

# Add shared proto directory to Python path
_shared_proto_path = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import payment_token_pb2

from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)

logger = structlog.get_logger(__name__)


class PaymentTokenServiceClient:
    """
    Client for calling the Payment Token Service /internal/decrypt endpoint.

    This client handles service-to-service communication with the Payment Token
    Service to decrypt payment tokens and retrieve sensitive payment card data.

    The client uses protobuf for serialization and includes proper service
    authentication and request correlation.
    """

    def __init__(
        self,
        base_url: str,
        service_auth_token: str,
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize the Payment Token Service client.

        Args:
            base_url: Base URL of the Payment Token Service (e.g., "http://localhost:8000")
            service_auth_token: Service authentication token for X-Service-Auth header
            timeout_seconds: Request timeout in seconds (default: 5.0)
        """
        self.base_url = base_url.rstrip("/")
        self.service_auth_token = service_auth_token
        self.timeout_seconds = timeout_seconds
        self.http_client = httpx.AsyncClient(timeout=timeout_seconds)

        logger.info(
            "payment_token_service_client_initialized",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    async def close(self) -> None:
        """Close the HTTP client connection pool."""
        await self.http_client.aclose()

    async def decrypt(
        self,
        payment_token: str,
        restaurant_id: str,
        requesting_service: str,
    ) -> payment_token_pb2.PaymentData:
        """
        Decrypt a payment token to retrieve payment card data.

        Calls the Payment Token Service /internal/v1/decrypt endpoint with
        proper authentication and serialization.

        Args:
            payment_token: Payment token to decrypt (format: pt_<uuid>)
            restaurant_id: Restaurant ID for authorization check
            requesting_service: Name of the requesting service (e.g., "auth-processor-worker")

        Returns:
            PaymentData protobuf message with decrypted card details

        Raises:
            TokenNotFound: 404 - token doesn't exist (TERMINAL error)
            TokenExpired: 410 - token expired (TERMINAL error)
            Forbidden: 403 - restaurant mismatch or unauthorized (TERMINAL error)
            ProcessorTimeout: 5xx or timeout (RETRYABLE error)
        """
        correlation_id = str(uuid.uuid4())

        # Build protobuf request
        request_proto = payment_token_pb2.DecryptPaymentTokenRequest(
            payment_token=payment_token,
            restaurant_id=restaurant_id,
            requesting_service=requesting_service,
        )

        url = f"{self.base_url}/internal/v1/decrypt"

        logger.info(
            "payment_token_decrypt_request",
            payment_token=payment_token,
            restaurant_id=restaurant_id,
            requesting_service=requesting_service,
            correlation_id=correlation_id,
            url=url,
        )

        try:
            response = await self.http_client.post(
                url,
                headers={
                    "Content-Type": "application/x-protobuf",
                    "X-Service-Auth": self.service_auth_token,
                    "X-Request-ID": correlation_id,
                },
                content=request_proto.SerializeToString(),
            )

            # Handle error responses
            if response.status_code == 404:
                logger.warning(
                    "payment_token_not_found",
                    payment_token=payment_token,
                    correlation_id=correlation_id,
                )
                raise TokenNotFound(f"Token {payment_token} not found")

            elif response.status_code == 410:
                logger.warning(
                    "payment_token_expired",
                    payment_token=payment_token,
                    correlation_id=correlation_id,
                )
                raise TokenExpired(f"Token {payment_token} expired")

            elif response.status_code == 403:
                logger.warning(
                    "payment_token_forbidden",
                    payment_token=payment_token,
                    restaurant_id=restaurant_id,
                    correlation_id=correlation_id,
                )
                raise Forbidden(f"Unauthorized access to token {payment_token}")

            elif response.status_code >= 500:
                logger.error(
                    "payment_token_service_error",
                    status_code=response.status_code,
                    correlation_id=correlation_id,
                )
                raise ProcessorTimeout(
                    f"Payment Token Service unavailable (status: {response.status_code})"
                )

            # Raise for other error status codes
            response.raise_for_status()

            # Parse successful response
            response_proto = payment_token_pb2.DecryptPaymentTokenResponse()
            response_proto.ParseFromString(response.content)

            logger.info(
                "payment_token_decrypt_success",
                payment_token=payment_token,
                correlation_id=correlation_id,
                card_last4=(
                    response_proto.payment_data.card_number[-4:]
                    if response_proto.payment_data.card_number
                    else None
                ),
            )

            return response_proto.payment_data

        except httpx.TimeoutException as e:
            logger.error(
                "payment_token_service_timeout",
                payment_token=payment_token,
                correlation_id=correlation_id,
                error=str(e),
            )
            raise ProcessorTimeout("Payment Token Service timeout") from e

        except httpx.RequestError as e:
            # Network errors, connection errors, etc.
            logger.error(
                "payment_token_service_request_error",
                payment_token=payment_token,
                correlation_id=correlation_id,
                error=str(e),
            )
            raise ProcessorTimeout(f"Payment Token Service request error: {e}") from e

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
