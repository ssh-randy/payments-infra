"""
Stripe payment processor integration.

IMPORTANT - MOCK PROCESSOR SYNC:
This implementation has a corresponding MockProcessor (mock_processor.py) that
mirrors its behavior for testing. When making changes to this file, please review
and update MockProcessor to maintain behavioral parity:

- Test card behaviors: Keep TEST_CARD_BEHAVIORS in mock_processor.py aligned with
  Stripe's official test cards: https://docs.stripe.com/testing#cards

- Response structure: Ensure MockProcessor returns AuthorizationResult objects
  with the same fields and metadata structure (see lines 174-189, 224-236 below)

- Error handling: Keep error patterns synchronized (see lines 208-271 below)

See mock_processor.py for detailed sync points marked with "SYNC POINT" comments.
"""

import structlog
from datetime import datetime
from typing import Any

import stripe
from stripe.error import (
    APIConnectionError,
    APIError,
    CardError,
    InvalidRequestError,
    RateLimitError,
)

from auth_processor_worker.models import (
    AuthStatus,
    AuthorizationResult,
    PaymentData,
    ProcessorTimeout,
)
from auth_processor_worker.processors.base import PaymentProcessor

logger = structlog.get_logger(__name__)


class StripeProcessor(PaymentProcessor):
    """
    Stripe payment processor implementation.

    Uses Stripe's Payment Intents API with manual capture to perform
    authorization-only transactions. This places a hold on the customer's
    card without capturing the funds.

    Reference:
    - https://docs.stripe.com/payments/place-a-hold-on-a-payment-method
    - https://docs.stripe.com/api/payment_intents
    """

    def __init__(self, api_key: str, timeout_seconds: int = 10) -> None:
        """
        Initialize Stripe processor.

        Args:
            api_key: Stripe secret API key (sk_test_... or sk_live_...)
            timeout_seconds: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        stripe.api_key = api_key
        stripe.max_network_retries = 0  # We handle retries at the worker level

        # Configure timeout at the HTTP client level
        # Note: Stripe's Python library uses requests internally, and timeout
        # must be configured via the default_http_client, not as a parameter
        # to individual API calls. For now, we'll remove the timeout parameter
        # from the create() call below.

    async def authorize(
        self,
        payment_data: PaymentData,
        amount_cents: int,
        currency: str,
        config: dict[str, Any],
    ) -> AuthorizationResult:
        """
        Authorize a payment using Stripe Payment Intents API.

        Creates a PaymentIntent with capture_method='manual' to authorize
        without capturing. The card details are provided directly using
        payment_method_data.

        Args:
            payment_data: Decrypted card information
            amount_cents: Amount to authorize in cents
            currency: ISO 4217 currency code (lowercase for Stripe)
            config: Additional Stripe-specific configuration

        Returns:
            AuthorizationResult with AUTHORIZED or DENIED status

        Raises:
            ProcessorTimeout: For transient errors (retryable)
        """
        try:
            logger.info(
                "stripe_authorization_starting",
                amount_cents=amount_cents,
                currency=currency,
            )

            # Create payment method data from decrypted card info
            payment_method_data = {
                "type": "card",
                "card": {
                    "number": payment_data.card_number,
                    "exp_month": payment_data.exp_month,
                    "exp_year": payment_data.exp_year,
                    "cvc": payment_data.cvv,
                },
                "billing_details": {
                    "name": payment_data.cardholder_name,
                },
            }

            # Add billing zip if provided
            if payment_data.billing_zip:
                payment_method_data["billing_details"]["address"] = {
                    "postal_code": payment_data.billing_zip
                }

            # Build PaymentIntent creation params
            intent_params: dict[str, Any] = {
                "amount": amount_cents,
                "currency": currency.lower(),
                "capture_method": "manual",  # Authorization only
                "payment_method_data": payment_method_data,
                "confirm": True,  # Confirm immediately
                # Provide a default return_url or use from config
                # This is required even for direct card payments in some Stripe configurations
                "return_url": config.get("return_url", "https://example.com/return"),
            }

            # Add optional statement descriptor suffix (note: Stripe changed their API)
            # For card payments, use statement_descriptor_suffix instead of statement_descriptor
            if statement_descriptor := config.get("statement_descriptor"):
                intent_params["statement_descriptor_suffix"] = statement_descriptor[:22]  # Max 22 chars

            # Add optional metadata
            if metadata := config.get("metadata"):
                intent_params["metadata"] = metadata

            # Create and confirm the payment intent
            # Note: Stripe's Python SDK doesn't accept a timeout parameter.
            # Timeout should be configured at the HTTP client level if needed.
            payment_intent = stripe.PaymentIntent.create(
                **intent_params,
                expand=["charges"]  # Expand charges to access authorization_code
            )

            # Check if the payment intent requires additional action
            # (e.g., 3D Secure authentication)
            if payment_intent.status == "requires_action":
                # For server-side integrations, we can't handle 3DS easily
                # This is a limitation - in production, you'd need a more sophisticated flow
                logger.warning(
                    "stripe_requires_action",
                    payment_intent_id=payment_intent.id,
                    next_action=payment_intent.next_action,
                )
                return AuthorizationResult(
                    status=AuthStatus.DENIED,
                    processor_name="stripe",
                    denial_code="requires_action",
                    denial_reason="Payment requires additional authentication",
                    processor_metadata={
                        "payment_intent_id": payment_intent.id,
                        "status": payment_intent.status,
                        "next_action": str(payment_intent.next_action),
                    },
                )

            # Check if authorization succeeded
            if payment_intent.status == "requires_capture":
                # Success! Authorization complete, waiting for capture
                logger.info(
                    "stripe_authorization_success",
                    payment_intent_id=payment_intent.id,
                    amount=payment_intent.amount,
                )

                # Extract charge details (should be available after confirmation)
                # Note: charges may not be available in all API versions or might not be expanded
                charge = None
                try:
                    if hasattr(payment_intent, 'charges') and payment_intent.charges and payment_intent.charges.data:
                        charge = payment_intent.charges.data[0]
                except (AttributeError, KeyError):
                    # Charges not available, which is OK - we have the payment_intent_id
                    pass

                return AuthorizationResult(
                    status=AuthStatus.AUTHORIZED,
                    processor_name="stripe",
                    processor_auth_id=payment_intent.id,
                    authorization_code=charge.authorization_code if charge else None,
                    authorized_amount_cents=payment_intent.amount,
                    currency=payment_intent.currency.upper(),
                    authorized_at=datetime.fromtimestamp(payment_intent.created),
                    processor_metadata={
                        "payment_intent_id": payment_intent.id,
                        "status": payment_intent.status,
                        "client_secret": payment_intent.client_secret,
                        "charge_id": charge.id if charge else None,
                        "payment_method_id": payment_intent.payment_method,
                    },
                )

            # If we get here, the status is unexpected
            logger.error(
                "stripe_unexpected_status",
                payment_intent_id=payment_intent.id,
                status=payment_intent.status,
            )
            return AuthorizationResult(
                status=AuthStatus.DENIED,
                processor_name="stripe",
                denial_code="unexpected_status",
                denial_reason=f"Unexpected payment intent status: {payment_intent.status}",
                processor_metadata={
                    "payment_intent_id": payment_intent.id,
                    "status": payment_intent.status,
                },
            )

        except CardError as e:
            # Card declined - this is NOT a failure, it's a normal business outcome
            # Extract decline_code from error object (it may not always be present)
            decline_code = None
            if hasattr(e, "error") and hasattr(e.error, "decline_code"):
                decline_code = e.error.decline_code
            elif e.json_body and "error" in e.json_body:
                decline_code = e.json_body["error"].get("decline_code")

            logger.info(
                "stripe_card_declined",
                error_code=e.code,
                decline_code=decline_code,
                message=e.user_message,
            )

            return AuthorizationResult(
                status=AuthStatus.DENIED,
                processor_name="stripe",
                denial_code=e.code or "card_declined",
                denial_reason=e.user_message or "Card was declined",
                processor_metadata={
                    "decline_code": decline_code,
                    "charge_id": e.charge if hasattr(e, "charge") else None,
                    "payment_intent_id": e.payment_intent.get("id")
                    if hasattr(e, "payment_intent") and e.payment_intent
                    else None,
                },
            )

        except InvalidRequestError as e:
            # Invalid request - this is a bug in our code, not a transient error
            # However, we should still treat it as retryable in case it's a config issue
            logger.error(
                "stripe_invalid_request",
                error=str(e),
                param=e.param,
                code=e.code,
            )
            raise ProcessorTimeout(f"Stripe invalid request: {e}") from e

        except RateLimitError as e:
            # Rate limited - retryable
            logger.warning("stripe_rate_limited", error=str(e))
            raise ProcessorTimeout(f"Stripe rate limit exceeded: {e}") from e

        except (APIError, APIConnectionError) as e:
            # API error or connection error - retryable
            logger.warning(
                "stripe_api_error",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise ProcessorTimeout(f"Stripe API error: {e}") from e

        except Exception as e:
            # Unexpected error - log and treat as retryable
            logger.error(
                "stripe_unexpected_error",
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise ProcessorTimeout(f"Unexpected Stripe error: {e}") from e
