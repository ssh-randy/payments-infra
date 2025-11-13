"""
Mock payment processor for end-to-end testing.

This mock processor implements the PaymentProcessor interface and simulates
various authorization scenarios without making real API calls. It's designed
to mirror the behavior of real processors (especially Stripe) for testing purposes.

IMPLEMENTATION NOTE - STRIPE LINKAGE:
This mock processor is intentionally structured to match the behavior patterns
of StripeProcessor (see stripe_processor.py). When the Stripe implementation
changes, this mock should be reviewed and updated to maintain behavioral parity.

Key areas to keep synchronized with Stripe implementation:
1. Payment method data structure (card details format) - stripe_processor.py:93-104
2. Authorization result fields and metadata - stripe_processor.py:174-189
3. Error handling patterns (CardError, timeout scenarios) - stripe_processor.py:208-271
4. Status codes and denial reasons - stripe_processor.py:224-236

STRIPE TEST CARDS REFERENCE:
These test card numbers are based on Stripe's official test cards:
https://docs.stripe.com/testing#cards

If Stripe updates their test card behaviors, update the TEST_CARD_BEHAVIORS
mapping below to maintain consistency.
"""

import asyncio
import structlog
import uuid
from datetime import datetime
from typing import Any

from auth_processor_worker.models import (
    AuthStatus,
    AuthorizationResult,
    PaymentData,
    ProcessorTimeout,
)
from auth_processor_worker.processors.base import PaymentProcessor

logger = structlog.get_logger(__name__)

# Test card behaviors - mirrors Stripe's test cards
# See: https://docs.stripe.com/testing#cards
# SYNC POINT: If Stripe adds new test card behaviors, add them here
TEST_CARD_BEHAVIORS = {
    # Success scenarios
    "4242424242424242": {
        "type": "success",
        "auth_code": "123456",
        "description": "Generic success - always authorizes",
    },
    "5555555555554444": {
        "type": "success",
        "auth_code": "789012",
        "description": "Mastercard success",
    },
    "378282246310005": {
        "type": "success",
        "auth_code": "345678",
        "description": "American Express success",
    },
    # Decline scenarios (mirrors Stripe CardError responses)
    # SYNC POINT: These map to Stripe's decline codes - see stripe_processor.py:208-236
    "4000000000000002": {
        "type": "decline",
        "code": "card_declined",
        "decline_code": "generic_decline",
        "reason": "Your card was declined",
        "description": "Generic decline",
    },
    "4000000000009995": {
        "type": "decline",
        "code": "card_declined",
        "decline_code": "insufficient_funds",
        "reason": "Your card has insufficient funds",
        "description": "Insufficient funds",
    },
    "4000000000000069": {
        "type": "decline",
        "code": "expired_card",
        "decline_code": "expired_card",
        "reason": "Your card has expired",
        "description": "Expired card",
    },
    "4000000000000127": {
        "type": "decline",
        "code": "incorrect_cvc",
        "decline_code": "incorrect_cvc",
        "reason": "Your card's security code is incorrect",
        "description": "Incorrect CVC",
    },
    "4000000000000341": {
        "type": "decline",
        "code": "card_declined",
        "decline_code": "lost_card",
        "reason": "Your card has been declined",
        "description": "Lost card",
    },
    "4000000000000226": {
        "type": "decline",
        "code": "card_declined",
        "decline_code": "fraudulent",
        "reason": "Your card has been declined",
        "description": "Fraudulent card",
    },
    # Timeout/error scenarios (mirrors ProcessorTimeout exceptions)
    # SYNC POINT: These map to retryable errors - see stripe_processor.py:249-271
    "4000000000000119": {
        "type": "timeout",
        "description": "Processing timeout - simulates 5xx error or network timeout",
    },
    "4000000000009987": {
        "type": "rate_limit",
        "description": "Rate limit - simulates 429 response",
    },
    # 3D Secure / requires_action (mirrors Stripe's requires_action status)
    # SYNC POINT: Maps to stripe_processor.py:140-158
    "4000002500003155": {
        "type": "requires_action",
        "description": "Requires 3D Secure authentication",
    },
}


class MockProcessor(PaymentProcessor):
    """
    Mock payment processor for testing.

    This processor simulates payment authorization without making real API calls.
    It's designed to mirror the behavior of StripeProcessor for testing purposes.

    SYNC WITH STRIPE:
    The structure and behavior of this class should match StripeProcessor where
    possible. Key synchronization points:

    1. __init__ parameters - see stripe_processor.py:40-51
    2. authorize() method signature - see base.py:18-24 and stripe_processor.py:59-84
    3. Response structure - see stripe_processor.py:174-189 (success) and 224-236 (decline)
    4. Error handling - see stripe_processor.py:208-271

    Args:
        config: Configuration dictionary with optional keys:
            - default_response: Default behavior for unknown cards ("authorized" or "declined")
            - latency_ms: Simulated processing latency in milliseconds
            - card_behaviors: Override default card behaviors with custom mapping
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        default_response: str = "authorized",
        latency_ms: int = 50,
    ) -> None:
        """
        Initialize mock processor.

        Args:
            config: Optional configuration dict (for consistency with real processors)
            default_response: Default response for unknown cards ("authorized" or "declined")
            latency_ms: Simulated latency in milliseconds (default: 50ms)
        """
        self.config = config or {}
        self.default_response = self.config.get("default_response", default_response)
        self.latency_ms = self.config.get("latency_ms", latency_ms)

        # Allow overriding card behaviors via config
        self.card_behaviors = self.config.get("card_behaviors", TEST_CARD_BEHAVIORS)

        logger.info(
            "mock_processor_initialized",
            default_response=self.default_response,
            latency_ms=self.latency_ms,
            custom_behaviors=len(self.card_behaviors) != len(TEST_CARD_BEHAVIORS),
        )

    async def authorize(
        self,
        payment_data: PaymentData,
        amount_cents: int,
        currency: str,
        config: dict[str, Any],
    ) -> AuthorizationResult:
        """
        Authorize a payment using mock logic.

        SYNC WITH STRIPE:
        This method mirrors the structure of StripeProcessor.authorize()
        (see stripe_processor.py:59-271) including:
        - Logging patterns
        - Payment method data extraction
        - Status checking logic
        - Error handling patterns

        The key difference is that this uses test card number lookup instead
        of making real API calls.

        Args:
            payment_data: Decrypted card information
            amount_cents: Amount to authorize in cents
            currency: ISO 4217 currency code
            config: Additional configuration (e.g., metadata, statement_descriptor)

        Returns:
            AuthorizationResult with AUTHORIZED or DENIED status

        Raises:
            ProcessorTimeout: For simulated transient errors (retryable)
        """
        # Simulate network latency
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        logger.info(
            "mock_authorization_starting",
            amount_cents=amount_cents,
            currency=currency,
            card_last_four=payment_data.card_number[-4:],
        )

        # Determine behavior based on card number
        card_number = payment_data.card_number
        behavior = self.card_behaviors.get(card_number)

        if behavior is None:
            # Unknown card - use default behavior
            logger.info(
                "mock_unknown_card",
                card_last_four=card_number[-4:],
                default_response=self.default_response,
            )
            # Normalize "declined" to "decline" for consistency
            default_type = "decline" if self.default_response == "declined" else self.default_response
            behavior = {"type": default_type}

        behavior_type = behavior["type"]

        # Handle timeout scenarios (retryable errors)
        # SYNC POINT: Mirrors stripe_processor.py:249-271
        if behavior_type == "timeout":
            logger.warning(
                "mock_timeout",
                card_last_four=card_number[-4:],
                description=behavior.get("description", "Timeout"),
            )
            raise ProcessorTimeout(
                f"Mock processor timeout: {behavior.get('description', 'Simulated timeout')}"
            )

        # Handle rate limit scenarios (retryable errors)
        # SYNC POINT: Mirrors stripe_processor.py:249-252
        if behavior_type == "rate_limit":
            logger.warning(
                "mock_rate_limited",
                card_last_four=card_number[-4:],
            )
            raise ProcessorTimeout("Mock processor rate limit exceeded")

        # Handle requires_action scenarios
        # SYNC POINT: Mirrors stripe_processor.py:140-158
        if behavior_type == "requires_action":
            logger.warning(
                "mock_requires_action",
                card_last_four=card_number[-4:],
            )
            return AuthorizationResult(
                status=AuthStatus.DENIED,
                processor_name="mock",
                denial_code="requires_action",
                denial_reason="Payment requires additional authentication",
                processor_metadata={
                    "mock_payment_intent_id": f"mock_pi_{uuid.uuid4().hex[:24]}",
                    "status": "requires_action",
                    "test_card": card_number,
                },
            )

        # Handle decline scenarios
        # SYNC POINT: Mirrors stripe_processor.py:208-236 (CardError handling)
        if behavior_type == "decline":
            decline_code = behavior.get("decline_code")
            error_code = behavior.get("code", "card_declined")
            reason = behavior.get("reason", "Card was declined")

            logger.info(
                "mock_card_declined",
                card_last_four=card_number[-4:],
                error_code=error_code,
                decline_code=decline_code,
                reason=reason,
            )

            # Generate mock IDs (mirrors Stripe's structure)
            mock_intent_id = f"mock_pi_{uuid.uuid4().hex[:24]}"
            mock_charge_id = f"mock_ch_{uuid.uuid4().hex[:24]}" if decline_code else None

            return AuthorizationResult(
                status=AuthStatus.DENIED,
                processor_name="mock",
                denial_code=error_code,
                denial_reason=reason,
                processor_metadata={
                    "decline_code": decline_code,
                    "charge_id": mock_charge_id,
                    "payment_intent_id": mock_intent_id,
                    "test_card": card_number,
                    "description": behavior.get("description"),
                },
            )

        # Handle success scenarios
        # SYNC POINT: Mirrors stripe_processor.py:161-189 (requires_capture status)
        if behavior_type == "success" or behavior_type == "authorized":
            auth_code = behavior.get("auth_code", f"{uuid.uuid4().int % 1000000:06d}")

            # Generate mock IDs that mirror Stripe's format
            mock_intent_id = f"mock_pi_{uuid.uuid4().hex[:24]}"
            mock_charge_id = f"mock_ch_{uuid.uuid4().hex[:24]}"
            mock_payment_method_id = f"mock_pm_{uuid.uuid4().hex[:24]}"
            mock_client_secret = f"{mock_intent_id}_secret_{uuid.uuid4().hex[:10]}"

            logger.info(
                "mock_authorization_success",
                payment_intent_id=mock_intent_id,
                amount=amount_cents,
                card_last_four=card_number[-4:],
            )

            return AuthorizationResult(
                status=AuthStatus.AUTHORIZED,
                processor_name="mock",
                processor_auth_id=mock_intent_id,
                authorization_code=auth_code,
                authorized_amount_cents=amount_cents,
                currency=currency.upper(),
                authorized_at=datetime.utcnow(),
                processor_metadata={
                    "payment_intent_id": mock_intent_id,
                    "status": "requires_capture",  # Mirrors Stripe's auth-only status
                    "client_secret": mock_client_secret,
                    "charge_id": mock_charge_id,
                    "payment_method_id": mock_payment_method_id,
                    "test_card": card_number,
                    "card_brand": self._get_card_brand(card_number),
                    "card_last4": card_number[-4:],
                    # Include config metadata if provided (mirrors stripe_processor.py:130-131)
                    **(config.get("metadata", {})),
                },
            )

        # Unknown behavior type - treat as error
        logger.error(
            "mock_unknown_behavior",
            behavior_type=behavior_type,
            card_last_four=card_number[-4:],
        )
        raise ProcessorTimeout(f"Unknown mock behavior type: {behavior_type}")

    def _get_card_brand(self, card_number: str) -> str:
        """
        Determine card brand from card number (simplified IIN lookup).

        This mirrors basic card brand detection that Stripe performs.
        SYNC POINT: If Stripe changes card brand detection logic, update this.

        Args:
            card_number: Full card number

        Returns:
            Card brand name (visa, mastercard, amex, discover, etc.)
        """
        if card_number.startswith("4"):
            return "visa"
        elif card_number.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        elif card_number.startswith(("34", "37")):
            return "amex"
        elif card_number.startswith("6011") or card_number.startswith(("644", "645", "646", "647", "648", "649", "65")):
            return "discover"
        else:
            return "unknown"
