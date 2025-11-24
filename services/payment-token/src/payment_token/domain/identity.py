"""Identity token generation using HMAC with KMS-managed keys.

This module provides functionality to generate identity tokens from credit card data
using HMAC-SHA256 with keys managed by AWS KMS. The identity token allows identifying
the same card across transactions without storing raw card data.

Security considerations:
- HMAC key is retrieved from KMS and never persisted
- Card data is normalized before hashing to ensure consistency
- PAN (Primary Account Number) is the primary identifier
- Additional card attributes can be included for stricter matching
"""

import hashlib
import hmac
import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)


class CardIdentityInput(NamedTuple):
    """Input data for identity token generation.

    Attributes:
        pan: Primary Account Number (card number) - required
        exp_month: Expiration month (01-12) - optional for stricter matching
        exp_year: Expiration year (4 digits) - optional for stricter matching
    """
    pan: str
    exp_month: str | None = None
    exp_year: str | None = None


class IdentityTokenResult(NamedTuple):
    """Result of identity token generation.

    Attributes:
        identity_hash: The HMAC-SHA256 hash (hex encoded)
        normalized_input: The normalized input string that was hashed
    """
    identity_hash: str
    normalized_input: str


def normalize_pan(pan: str) -> str:
    """Normalize PAN by removing spaces and dashes.

    Args:
        pan: Card number potentially with spaces or dashes

    Returns:
        Normalized PAN with only digits

    Raises:
        ValueError: If PAN is invalid (empty or contains non-digit chars after normalization)
    """
    if not pan:
        raise ValueError("PAN cannot be empty")

    # Remove spaces, dashes, and any whitespace
    normalized = re.sub(r'[\s\-]', '', pan)

    # Validate it contains only digits
    if not normalized.isdigit():
        raise ValueError("PAN must contain only digits after normalization")

    # Validate length (typical card numbers are 13-19 digits)
    if len(normalized) < 13 or len(normalized) > 19:
        raise ValueError(f"PAN length must be 13-19 digits, got {len(normalized)}")

    return normalized


def normalize_exp_month(exp_month: str | None) -> str:
    """Normalize expiration month to 2-digit format.

    Args:
        exp_month: Month as string (e.g., "1", "01", "12")

    Returns:
        2-digit month string (e.g., "01", "12")

    Raises:
        ValueError: If month is invalid
    """
    if not exp_month:
        return ""

    month_str = exp_month.strip()

    # Handle numeric string
    try:
        month_int = int(month_str)
        if month_int < 1 or month_int > 12:
            raise ValueError(f"Invalid month: {month_str}")
        return f"{month_int:02d}"
    except ValueError as e:
        if "Invalid month" in str(e):
            raise
        raise ValueError(f"Month must be numeric: {month_str}") from e


def normalize_exp_year(exp_year: str | None) -> str:
    """Normalize expiration year to 4-digit format.

    Args:
        exp_year: Year as string (e.g., "25", "2025")

    Returns:
        4-digit year string (e.g., "2025")

    Raises:
        ValueError: If year is invalid
    """
    if not exp_year:
        return ""

    year_str = exp_year.strip()

    try:
        year_int = int(year_str)

        # Handle 2-digit year (assume 2000s)
        if year_int < 100:
            year_int = 2000 + year_int

        # Reasonable year range (2020-2099)
        if year_int < 2020 or year_int > 2099:
            raise ValueError(f"Year out of valid range: {year_int}")

        return str(year_int)
    except ValueError as e:
        if "Year out of valid range" in str(e):
            raise
        raise ValueError(f"Year must be numeric: {year_str}") from e


def build_identity_input(card_input: CardIdentityInput) -> str:
    """Build the normalized input string for HMAC calculation.

    The input string format is:
    - PAN only: "pan:<normalized_pan>"
    - With expiration: "pan:<normalized_pan>|exp:<mm>/<yyyy>"

    Args:
        card_input: Card identity input data

    Returns:
        Normalized input string for hashing
    """
    normalized_pan = normalize_pan(card_input.pan)

    parts = [f"pan:{normalized_pan}"]

    # Include expiration if both month and year are provided
    if card_input.exp_month and card_input.exp_year:
        normalized_month = normalize_exp_month(card_input.exp_month)
        normalized_year = normalize_exp_year(card_input.exp_year)
        parts.append(f"exp:{normalized_month}/{normalized_year}")

    return "|".join(parts)


def calculate_identity_hmac(
    card_input: CardIdentityInput,
    hmac_key: bytes,
) -> IdentityTokenResult:
    """Calculate HMAC-SHA256 identity hash for card data.

    This function takes card data and an HMAC key (from KMS) to produce
    a deterministic hash that can be used to identify the same card
    across transactions.

    Args:
        card_input: Card identity input data
        hmac_key: 32-byte HMAC key from KMS

    Returns:
        IdentityTokenResult with hash and normalized input

    Raises:
        ValueError: If card_input is invalid or hmac_key is wrong length
    """
    if len(hmac_key) != 32:
        raise ValueError(f"HMAC key must be 32 bytes, got {len(hmac_key)}")

    # Build normalized input
    normalized_input = build_identity_input(card_input)

    # Calculate HMAC-SHA256
    identity_hash = hmac.new(
        hmac_key,
        normalized_input.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    logger.debug(f"Generated identity hash for card ending in {card_input.pan[-4:]}")

    return IdentityTokenResult(
        identity_hash=identity_hash,
        normalized_input=normalized_input
    )


