"""Base interface for payment processors."""

from abc import ABC, abstractmethod
from typing import Any

from auth_processor_worker.models import AuthorizationResult, PaymentData


class PaymentProcessor(ABC):
    """
    Abstract base class for payment processor integrations.

    All payment processors (Stripe, Chase, Worldpay, etc.) must implement
    this interface to ensure consistent behavior across the worker service.
    """

    @abstractmethod
    async def authorize(
        self,
        payment_data: PaymentData,
        amount_cents: int,
        currency: str,
        config: dict[str, Any],
    ) -> AuthorizationResult:
        """
        Authorize a payment with the processor.

        This method performs an authorization-only transaction (capture=False),
        which places a hold on the customer's payment method without actually
        charging them. The funds can be captured later via a separate capture call.

        Args:
            payment_data: Decrypted payment information (card details)
            amount_cents: Amount to authorize in cents (e.g., 1000 = $10.00)
            currency: ISO 4217 currency code (e.g., "USD", "EUR")
            config: Processor-specific configuration (API keys, endpoints, etc.)

        Returns:
            AuthorizationResult with either AUTHORIZED or DENIED status.

        Raises:
            ProcessorTimeout: For transient errors (5xx, timeouts, network errors).
                             These should be retried with exponential backoff.

        Note:
            Card declines are NOT exceptions - they return AuthorizationResult
            with status=DENIED and appropriate denial_code/denial_reason.
        """
        pass
