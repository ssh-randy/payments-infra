"""Custom exceptions for Auth Processor Worker Service."""


class ProcessorError(Exception):
    """Base exception for processor-related errors."""

    pass


class ProcessorTimeout(ProcessorError):
    """
    Raised when a payment processor times out or returns a transient error.

    This is a RETRYABLE error. The worker should retry the request with
    exponential backoff up to MAX_RETRIES.

    Examples:
    - Processor API returns 5xx errors
    - Processor API returns 429 (rate limit)
    - Network timeout
    - Connection errors
    """

    pass


class TokenNotFound(ProcessorError):
    """
    Raised when Payment Token Service returns 404 (token not found).

    This is a TERMINAL error. The request should be sent to DLQ
    and marked as FAILED.
    """

    pass


class TokenExpired(ProcessorError):
    """
    Raised when Payment Token Service returns 410 (token expired).

    This is a TERMINAL error. The request should be sent to DLQ
    and marked as FAILED.
    """

    pass


class Forbidden(ProcessorError):
    """
    Raised when Payment Token Service returns 403 (forbidden/unauthorized).

    This is a TERMINAL error indicating authorization failure (e.g., restaurant
    mismatch or invalid service authentication).
    """

    pass
