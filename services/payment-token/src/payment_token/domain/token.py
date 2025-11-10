"""Domain models for payment tokens.

This module contains the core domain entities and value objects for the
payment token service. These models represent the business logic layer
and are independent of infrastructure concerns.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


class TokenError(Exception):
    """Base exception for token-related errors."""

    pass


class TokenExpiredError(TokenError):
    """Exception raised when a token has expired."""

    pass


class TokenOwnershipError(TokenError):
    """Exception raised when token ownership validation fails."""

    pass


@dataclass(frozen=True)
class PaymentData:
    """Decrypted payment card data (highly sensitive - PCI scope).

    This is a domain representation of the PaymentData protobuf message.
    All fields are immutable to prevent accidental modification of sensitive data.

    Attributes:
        card_number: Full card number (PAN)
        exp_month: Expiration month (MM format, e.g., "01")
        exp_year: Expiration year (YYYY format, e.g., "2025")
        cvv: Card verification value (CVV/CVC)
        cardholder_name: Name as it appears on the card
        billing_address: Optional billing address as dict
    """

    card_number: str
    exp_month: str
    exp_year: str
    cvv: str
    cardholder_name: str
    billing_address: Optional[dict] = None

    def __post_init__(self):
        """Validate payment data fields."""
        if not self.card_number or not self.card_number.isdigit():
            raise ValueError("card_number must be numeric")

        if len(self.card_number) < 13 or len(self.card_number) > 19:
            raise ValueError("card_number must be 13-19 digits")

        if not self.exp_month or not self.exp_month.isdigit() or len(self.exp_month) != 2:
            raise ValueError("exp_month must be 2-digit numeric (MM)")

        month = int(self.exp_month)
        if month < 1 or month > 12:
            raise ValueError("exp_month must be between 01 and 12")

        if not self.exp_year or not self.exp_year.isdigit() or len(self.exp_year) != 4:
            raise ValueError("exp_year must be 4-digit numeric (YYYY)")

        if not self.cvv or not self.cvv.isdigit() or len(self.cvv) not in [3, 4]:
            raise ValueError("cvv must be 3 or 4 digits")

        if not self.cardholder_name or not self.cardholder_name.strip():
            raise ValueError("cardholder_name cannot be empty")

    def to_bytes(self) -> bytes:
        """Serialize payment data to bytes for encryption.

        Returns a deterministic byte representation suitable for encryption.
        Format: card_number|exp_month|exp_year|cvv|cardholder_name

        Returns:
            Bytes representation of payment data
        """
        parts = [
            self.card_number,
            self.exp_month,
            self.exp_year,
            self.cvv,
            self.cardholder_name,
        ]
        return "|".join(parts).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PaymentData":
        """Deserialize payment data from bytes.

        Args:
            data: Byte representation from to_bytes()

        Returns:
            PaymentData instance

        Raises:
            ValueError: If data format is invalid
        """
        try:
            text = data.decode("utf-8")
            parts = text.split("|")

            if len(parts) != 5:
                raise ValueError(f"Expected 5 parts, got {len(parts)}")

            return cls(
                card_number=parts[0],
                exp_month=parts[1],
                exp_year=parts[2],
                cvv=parts[3],
                cardholder_name=parts[4],
            )
        except (UnicodeDecodeError, IndexError) as e:
            raise ValueError(f"Invalid payment data format: {e}") from e


@dataclass(frozen=True)
class TokenMetadata:
    """Non-sensitive token metadata for display purposes.

    This data is safe to store unencrypted and can be returned
    to clients without decryption.

    Attributes:
        card_brand: Card network (e.g., "visa", "mastercard", "amex")
        last4: Last 4 digits of card number
        exp_month: Expiration month (MM format)
        exp_year: Expiration year (YYYY format)
    """

    card_brand: Optional[str] = None
    last4: Optional[str] = None
    exp_month: Optional[str] = None
    exp_year: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        """Convert metadata to dictionary for storage/serialization.

        Returns:
            Dictionary with non-None values
        """
        result = {}
        if self.card_brand:
            result["card_brand"] = self.card_brand
        if self.last4:
            result["last4"] = self.last4
        if self.exp_month:
            result["exp_month"] = self.exp_month
        if self.exp_year:
            result["exp_year"] = self.exp_year
        return result

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "TokenMetadata":
        """Create metadata from dictionary.

        Args:
            data: Dictionary with metadata fields (can be None)

        Returns:
            TokenMetadata instance (empty if data is None)
        """
        if not data:
            return cls()

        return cls(
            card_brand=data.get("card_brand"),
            last4=data.get("last4"),
            exp_month=data.get("exp_month"),
            exp_year=data.get("exp_year"),
        )

    @classmethod
    def from_payment_data(cls, payment_data: PaymentData) -> "TokenMetadata":
        """Extract non-sensitive metadata from payment data.

        Args:
            payment_data: Decrypted payment data

        Returns:
            TokenMetadata with extracted fields
        """
        # Detect card brand from first digit(s)
        card_brand = _detect_card_brand(payment_data.card_number)

        return cls(
            card_brand=card_brand,
            last4=payment_data.card_number[-4:],
            exp_month=payment_data.exp_month,
            exp_year=payment_data.exp_year,
        )


@dataclass
class PaymentToken:
    """Core payment token domain entity.

    Represents a tokenized payment card with encrypted data and metadata.
    This is the aggregate root for the payment token bounded context.

    Attributes:
        payment_token: Token ID in format pt_{uuid}
        restaurant_id: UUID of restaurant/merchant that owns this token
        encrypted_payment_data: Payment data encrypted with service key
        encryption_key_version: Version of encryption key used
        device_token: Original device identifier (for audit)
        created_at: When token was created
        expires_at: When token expires
        metadata: Non-sensitive display metadata
    """

    payment_token: str
    restaurant_id: str
    encrypted_payment_data: bytes
    encryption_key_version: str
    device_token: str
    created_at: datetime
    expires_at: datetime
    metadata: TokenMetadata = field(default_factory=TokenMetadata)

    def __post_init__(self):
        """Validate token fields."""
        if not self.payment_token.startswith("pt_"):
            raise ValueError("payment_token must start with 'pt_'")

        if not self.restaurant_id:
            raise ValueError("restaurant_id cannot be empty")

        if not self.encrypted_payment_data:
            raise ValueError("encrypted_payment_data cannot be empty")

        if not self.encryption_key_version:
            raise ValueError("encryption_key_version cannot be empty")

        if not self.device_token:
            raise ValueError("device_token cannot be empty")

        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

    @staticmethod
    def generate_token_id() -> str:
        """Generate a new payment token ID.

        Returns:
            Token ID in format pt_{uuid}
        """
        return f"pt_{uuid.uuid4()}"

    def is_expired(self) -> bool:
        """Check if token has expired.

        Returns:
            True if token has expired, False otherwise
        """
        now = datetime.now(timezone.utc)
        # Handle both timezone-aware and timezone-naive datetimes
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return now > expires_at

    def validate_ownership(self, restaurant_id: str) -> None:
        """Validate that the given restaurant owns this token.

        Args:
            restaurant_id: Restaurant ID to validate

        Raises:
            TokenOwnershipError: If restaurant doesn't own this token
        """
        if self.restaurant_id != restaurant_id:
            raise TokenOwnershipError(
                f"Token {self.payment_token} does not belong to restaurant {restaurant_id}"
            )

    def validate_not_expired(self) -> None:
        """Validate that token has not expired.

        Raises:
            TokenExpiredError: If token has expired
        """
        if self.is_expired():
            raise TokenExpiredError(
                f"Token {self.payment_token} expired at {self.expires_at}"
            )

    @classmethod
    def create(
        cls,
        restaurant_id: str,
        encrypted_payment_data: bytes,
        encryption_key_version: str,
        device_token: str,
        metadata: Optional[TokenMetadata] = None,
        expiration_hours: int = 24,
    ) -> "PaymentToken":
        """Create a new payment token.

        This is a factory method that generates a new token ID and sets
        appropriate timestamps.

        Args:
            restaurant_id: UUID of restaurant/merchant
            encrypted_payment_data: Payment data encrypted with service key
            encryption_key_version: Version of encryption key used
            device_token: Device identifier
            metadata: Optional non-sensitive metadata
            expiration_hours: Hours until token expires (default 24)

        Returns:
            New PaymentToken instance
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expiration_hours)

        return cls(
            payment_token=cls.generate_token_id(),
            restaurant_id=restaurant_id,
            encrypted_payment_data=encrypted_payment_data,
            encryption_key_version=encryption_key_version,
            device_token=device_token,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or TokenMetadata(),
        )


def _detect_card_brand(card_number: str) -> str:
    """Detect card brand from card number.

    Uses industry-standard card number prefixes to detect brand.

    Args:
        card_number: Full card number

    Returns:
        Card brand name (lowercase)
    """
    # Remove any spaces or dashes
    card_number = card_number.replace(" ", "").replace("-", "")

    if not card_number:
        return "unknown"

    # Visa: starts with 4
    if card_number.startswith("4"):
        return "visa"

    # Mastercard: starts with 51-55 or 2221-2720
    if card_number.startswith(("51", "52", "53", "54", "55")):
        return "mastercard"
    if len(card_number) >= 4:
        prefix = int(card_number[:4])
        if 2221 <= prefix <= 2720:
            return "mastercard"

    # American Express: starts with 34 or 37
    if card_number.startswith(("34", "37")):
        return "amex"

    # Discover: starts with 6011, 622126-622925, 644-649, or 65
    if card_number.startswith("6011") or card_number.startswith("65"):
        return "discover"
    if len(card_number) >= 6:
        prefix = int(card_number[:6])
        if 622126 <= prefix <= 622925:
            return "discover"
    if len(card_number) >= 3:
        prefix = int(card_number[:3])
        if 644 <= prefix <= 649:
            return "discover"

    return "unknown"
