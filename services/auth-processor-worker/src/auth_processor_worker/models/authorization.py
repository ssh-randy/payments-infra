"""Authorization domain models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class AuthStatus(str, Enum):
    """Authorization status."""

    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"


@dataclass
class PaymentData:
    """
    Decrypted payment data from Payment Token Service.

    This represents the sensitive card information that has been
    decrypted and is ready to be sent to the payment processor.
    """

    card_number: str
    exp_month: int
    exp_year: int
    cvv: str
    cardholder_name: str
    billing_zip: str | None = None


@dataclass
class AuthorizationResult:
    """
    Result from a payment processor authorization attempt.

    This is the unified interface that all payment processors must return.
    It contains either a successful authorization or a denial, but NOT
    a failure (failures raise exceptions).
    """

    status: AuthStatus
    processor_name: str

    # Fields populated on AUTHORIZED status
    processor_auth_id: str | None = None
    authorization_code: str | None = None
    authorized_amount_cents: int | None = None
    currency: str | None = None
    authorized_at: datetime | None = None

    # Fields populated on DENIED status
    denial_code: str | None = None
    denial_reason: str | None = None

    # Optional processor-specific metadata
    processor_metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate that required fields are present based on status."""
        if self.status == AuthStatus.AUTHORIZED:
            if not self.processor_auth_id:
                raise ValueError("processor_auth_id required for AUTHORIZED status")
            if self.authorized_amount_cents is None:
                raise ValueError("authorized_amount_cents required for AUTHORIZED status")
        elif self.status == AuthStatus.DENIED:
            if not self.denial_code:
                raise ValueError("denial_code required for DENIED status")
