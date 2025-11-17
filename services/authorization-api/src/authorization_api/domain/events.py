"""Domain events for authorization requests."""

import json
from dataclasses import dataclass
from typing import Any
import uuid
from datetime import datetime

from payments_proto.payments.v1.events_pb2 import (
    AuthRequestCreated,
    AuthAttemptStarted,
    AuthResponseReceived,
    AuthAttemptFailed,
    AuthVoidRequested,
    AuthRequestExpired,
    AuthRequestQueuedMessage,
    VoidRequestQueuedMessage,
)
from payments_proto.payments.v1.authorization_pb2 import AuthStatus, AuthorizationResult


@dataclass
class Event:
    """Base event class."""

    event_id: uuid.UUID
    aggregate_id: uuid.UUID
    aggregate_type: str
    event_type: str
    event_data: bytes  # Serialized protobuf
    sequence_number: int
    metadata: dict[str, Any] | None = None


def create_auth_request_created_event(
    auth_request_id: uuid.UUID,
    payment_token: str,
    restaurant_id: uuid.UUID,
    amount_cents: int,
    currency: str,
    metadata: dict[str, str] | None = None,
) -> bytes:
    """Create AuthRequestCreated event protobuf.

    Args:
        auth_request_id: The authorization request ID
        payment_token: Payment token from token service
        restaurant_id: Restaurant UUID
        amount_cents: Amount in cents
        currency: ISO currency code
        metadata: Optional metadata

    Returns:
        Serialized protobuf bytes
    """
    event = AuthRequestCreated(
        auth_request_id=str(auth_request_id),
        payment_token=payment_token,
        restaurant_id=str(restaurant_id),
        amount_cents=amount_cents,
        currency=currency,
        created_at=int(datetime.utcnow().timestamp()),
    )

    if metadata:
        # Convert metadata values to strings (protobuf map fields only accept strings)
        for key, value in metadata.items():
            if isinstance(value, (dict, list)):
                # Serialize complex types to JSON
                event.metadata[key] = json.dumps(value)
            else:
                event.metadata[key] = str(value)

    return event.SerializeToString()


def create_auth_void_requested_event(
    auth_request_id: uuid.UUID,
    reason: str,
) -> bytes:
    """Create AuthVoidRequested event protobuf.

    Args:
        auth_request_id: The authorization request ID
        reason: Reason for void

    Returns:
        Serialized protobuf bytes
    """
    event = AuthVoidRequested(
        auth_request_id=str(auth_request_id),
        reason=reason,
        requested_at=int(datetime.utcnow().timestamp()),
    )

    return event.SerializeToString()


def create_auth_request_queued_message(
    auth_request_id: uuid.UUID,
    restaurant_id: uuid.UUID,
) -> bytes:
    """Create AuthRequestQueuedMessage protobuf for outbox.

    Args:
        auth_request_id: The authorization request ID
        restaurant_id: Restaurant UUID

    Returns:
        Serialized protobuf bytes
    """
    message = AuthRequestQueuedMessage(
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        created_at=int(datetime.utcnow().timestamp()),
    )

    return message.SerializeToString()


def create_void_request_queued_message(
    auth_request_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    reason: str,
) -> bytes:
    """Create VoidRequestQueuedMessage protobuf for outbox.

    Args:
        auth_request_id: The authorization request ID
        restaurant_id: Restaurant UUID
        reason: Reason for void

    Returns:
        Serialized protobuf bytes
    """
    message = VoidRequestQueuedMessage(
        auth_request_id=str(auth_request_id),
        restaurant_id=str(restaurant_id),
        reason=reason,
        created_at=int(datetime.utcnow().timestamp()),
    )

    return message.SerializeToString()
