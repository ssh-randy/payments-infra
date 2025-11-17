"""Integration tests for POST /authorize endpoint with real database.

These tests verify:
- Atomic transaction behavior with real database
- Idempotency with database constraints
- Event store writes
- Read model updates
- Outbox pattern reliability
"""

import uuid

import pytest
from payments_proto.payments.v1.authorization_pb2 import AuthorizeRequest, AuthorizeResponse, AuthStatus
from payments_proto.payments.v1.events_pb2 import AuthRequestCreated, AuthRequestQueuedMessage

from authorization_api.api.routes.authorize import (
    check_idempotency,
    write_idempotency_key,
)
from authorization_api.domain.events import (
    create_auth_request_created_event,
    create_auth_request_queued_message,
)
from authorization_api.domain.read_models import (
    create_auth_request_state,
    get_auth_request_state,
)
from authorization_api.infrastructure.event_store import write_event
from authorization_api.infrastructure.outbox import write_outbox_message


@pytest.mark.asyncio
async def test_atomic_transaction_all_writes(
    db_conn, test_restaurant_id, test_payment_token, test_idempotency_key
):
    """Test that all 4 writes happen atomically in a transaction."""
    auth_request_id = uuid.uuid4()
    event_id = uuid.uuid4()
    amount_cents = 1050
    currency = "USD"

    # Start transaction
    async with db_conn.transaction():
        # 1. Write event
        event_data = create_auth_request_created_event(
            auth_request_id=auth_request_id,
            payment_token=test_payment_token,
            restaurant_id=test_restaurant_id,
            amount_cents=amount_cents,
            currency=currency,
        )

        await write_event(
            conn=db_conn,
            event_id=event_id,
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type="AuthRequestCreated",
            event_data=event_data,
            sequence_number=1,
        )

        # 2. Write read model
        await create_auth_request_state(
            conn=db_conn,
            auth_request_id=auth_request_id,
            restaurant_id=test_restaurant_id,
            payment_token=test_payment_token,
            amount_cents=amount_cents,
            currency=currency,
        )

        # 3. Write outbox
        queue_message = create_auth_request_queued_message(
            auth_request_id=auth_request_id,
            restaurant_id=test_restaurant_id,
        )

        await write_outbox_message(
            conn=db_conn,
            aggregate_id=auth_request_id,
            message_type="auth_request_queued",
            payload=queue_message,
        )

        # 4. Write idempotency key
        await write_idempotency_key(
            conn=db_conn,
            idempotency_key=test_idempotency_key,
            auth_request_id=auth_request_id,
            restaurant_id=test_restaurant_id,
        )

        # Transaction commits here

    # Verify all writes persisted
    # Check event
    event_row = await db_conn.fetchrow(
        "SELECT * FROM payment_events WHERE event_id = $1", event_id
    )
    assert event_row is not None
    assert event_row["aggregate_id"] == auth_request_id
    assert event_row["event_type"] == "AuthRequestCreated"
    assert event_row["sequence_number"] == 1

    # Verify event data can be deserialized
    event_proto = AuthRequestCreated()
    event_proto.ParseFromString(event_row["event_data"])
    assert event_proto.auth_request_id == str(auth_request_id)
    assert event_proto.amount_cents == amount_cents

    # Check read model
    state_row = await get_auth_request_state(db_conn, auth_request_id)
    assert state_row is not None
    assert state_row["status"] == "PENDING"
    assert state_row["amount_cents"] == amount_cents
    assert state_row["payment_token"] == test_payment_token

    # Check outbox
    outbox_row = await db_conn.fetchrow(
        "SELECT * FROM outbox WHERE aggregate_id = $1", auth_request_id
    )
    assert outbox_row is not None
    assert outbox_row["message_type"] == "auth_request_queued"
    assert outbox_row["processed_at"] is None  # Not processed yet

    # Verify outbox payload can be deserialized
    queue_proto = AuthRequestQueuedMessage()
    queue_proto.ParseFromString(outbox_row["payload"])
    assert queue_proto.auth_request_id == str(auth_request_id)

    # Check idempotency key
    idem_row = await db_conn.fetchrow(
        "SELECT * FROM auth_idempotency_keys WHERE idempotency_key = $1",
        test_idempotency_key,
    )
    assert idem_row is not None
    assert idem_row["auth_request_id"] == auth_request_id


@pytest.mark.asyncio
async def test_transaction_rollback_prevents_partial_writes(
    db_conn, test_restaurant_id, test_payment_token, test_idempotency_key
):
    """Test that transaction rollback prevents any writes from persisting."""
    auth_request_id = uuid.uuid4()
    event_id = uuid.uuid4()

    try:
        async with db_conn.transaction():
            # Write event
            event_data = create_auth_request_created_event(
                auth_request_id=auth_request_id,
                payment_token=test_payment_token,
                restaurant_id=test_restaurant_id,
                amount_cents=1050,
                currency="USD",
            )

            await write_event(
                conn=db_conn,
                event_id=event_id,
                aggregate_id=auth_request_id,
                aggregate_type="auth_request",
                event_type="AuthRequestCreated",
                event_data=event_data,
                sequence_number=1,
            )

            # Write read model
            await create_auth_request_state(
                conn=db_conn,
                auth_request_id=auth_request_id,
                restaurant_id=test_restaurant_id,
                payment_token=test_payment_token,
                amount_cents=1050,
                currency="USD",
            )

            # Simulate error before completing all writes
            raise Exception("Simulated error")

    except Exception:
        pass  # Expected

    # Verify NO writes persisted
    event_row = await db_conn.fetchrow(
        "SELECT * FROM payment_events WHERE event_id = $1", event_id
    )
    assert event_row is None

    state_row = await get_auth_request_state(db_conn, auth_request_id)
    assert state_row is None


@pytest.mark.asyncio
async def test_idempotency_database_constraint(
    db_conn, test_restaurant_id, test_payment_token, test_idempotency_key
):
    """Test that database constraints prevent duplicate idempotency keys."""
    auth_request_id = uuid.uuid4()

    # Write first idempotency key
    await write_idempotency_key(
        conn=db_conn,
        idempotency_key=test_idempotency_key,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Try to write same key again (should fail with constraint violation)
    with pytest.raises(Exception) as exc_info:
        await write_idempotency_key(
            conn=db_conn,
            idempotency_key=test_idempotency_key,
            auth_request_id=uuid.uuid4(),  # Different ID
            restaurant_id=test_restaurant_id,
        )

    # Verify it's a unique constraint violation
    assert "unique" in str(exc_info.value).lower() or "duplicate" in str(
        exc_info.value
    ).lower()


@pytest.mark.asyncio
async def test_idempotency_check_returns_existing(
    db_conn, test_restaurant_id, test_payment_token, test_idempotency_key
):
    """Test that idempotency check returns existing auth_request_id."""
    auth_request_id = uuid.uuid4()

    # Create initial request
    await write_idempotency_key(
        conn=db_conn,
        idempotency_key=test_idempotency_key,
        auth_request_id=auth_request_id,
        restaurant_id=test_restaurant_id,
    )

    # Check idempotency
    existing_id = await check_idempotency(
        db_conn, test_idempotency_key, test_restaurant_id
    )

    assert existing_id == auth_request_id


@pytest.mark.asyncio
async def test_idempotency_check_returns_none_for_new_key(
    db_conn, test_restaurant_id, test_idempotency_key
):
    """Test that idempotency check returns None for new key."""
    existing_id = await check_idempotency(
        db_conn, test_idempotency_key, test_restaurant_id
    )

    assert existing_id is None


@pytest.mark.asyncio
async def test_event_sequence_numbers(db_conn, test_restaurant_id, test_payment_token):
    """Test that event sequence numbers are enforced correctly."""
    auth_request_id = uuid.uuid4()

    # Write first event (sequence 1)
    event_data_1 = create_auth_request_created_event(
        auth_request_id=auth_request_id,
        payment_token=test_payment_token,
        restaurant_id=test_restaurant_id,
        amount_cents=1050,
        currency="USD",
    )

    await write_event(
        conn=db_conn,
        event_id=uuid.uuid4(),
        aggregate_id=auth_request_id,
        aggregate_type="auth_request",
        event_type="AuthRequestCreated",
        event_data=event_data_1,
        sequence_number=1,
    )

    # Write second event (sequence 2)
    from authorization_api.domain.events import create_auth_void_requested_event

    event_data_2 = create_auth_void_requested_event(
        auth_request_id=auth_request_id,
        reason="customer_cancelled",
    )

    await write_event(
        conn=db_conn,
        event_id=uuid.uuid4(),
        aggregate_id=auth_request_id,
        aggregate_type="auth_request",
        event_type="AuthVoidRequested",
        event_data=event_data_2,
        sequence_number=2,
    )

    # Verify both events exist with correct sequence
    events = await db_conn.fetch(
        "SELECT * FROM payment_events WHERE aggregate_id = $1 ORDER BY sequence_number",
        auth_request_id,
    )

    assert len(events) == 2
    assert events[0]["sequence_number"] == 1
    assert events[0]["event_type"] == "AuthRequestCreated"
    assert events[1]["sequence_number"] == 2
    assert events[1]["event_type"] == "AuthVoidRequested"


@pytest.mark.asyncio
async def test_duplicate_sequence_number_fails(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test that duplicate sequence numbers are rejected."""
    auth_request_id = uuid.uuid4()

    # Write first event
    event_data = create_auth_request_created_event(
        auth_request_id=auth_request_id,
        payment_token=test_payment_token,
        restaurant_id=test_restaurant_id,
        amount_cents=1050,
        currency="USD",
    )

    await write_event(
        conn=db_conn,
        event_id=uuid.uuid4(),
        aggregate_id=auth_request_id,
        aggregate_type="auth_request",
        event_type="AuthRequestCreated",
        event_data=event_data,
        sequence_number=1,
    )

    # Try to write another event with same sequence (should fail)
    with pytest.raises(Exception) as exc_info:
        await write_event(
            conn=db_conn,
            event_id=uuid.uuid4(),
            aggregate_id=auth_request_id,
            aggregate_type="auth_request",
            event_type="AuthRequestCreated",
            event_data=event_data,
            sequence_number=1,  # Duplicate!
        )

    # Verify it's a unique constraint violation
    assert "unique" in str(exc_info.value).lower() or "duplicate" in str(
        exc_info.value
    ).lower()


@pytest.mark.asyncio
async def test_outbox_multiple_messages(db_conn, test_restaurant_id):
    """Test that multiple outbox messages can be written."""
    auth_request_id_1 = uuid.uuid4()
    auth_request_id_2 = uuid.uuid4()

    # Write first outbox message
    queue_message_1 = create_auth_request_queued_message(
        auth_request_id=auth_request_id_1,
        restaurant_id=test_restaurant_id,
    )

    await write_outbox_message(
        conn=db_conn,
        aggregate_id=auth_request_id_1,
        message_type="auth_request_queued",
        payload=queue_message_1,
    )

    # Write second outbox message
    queue_message_2 = create_auth_request_queued_message(
        auth_request_id=auth_request_id_2,
        restaurant_id=test_restaurant_id,
    )

    await write_outbox_message(
        conn=db_conn,
        aggregate_id=auth_request_id_2,
        message_type="auth_request_queued",
        payload=queue_message_2,
    )

    # Verify both messages exist
    messages = await db_conn.fetch(
        "SELECT * FROM outbox WHERE processed_at IS NULL ORDER BY created_at"
    )

    assert len(messages) >= 2  # At least our 2 messages


@pytest.mark.asyncio
async def test_read_model_status_constraint(
    db_conn, test_restaurant_id, test_payment_token
):
    """Test that read model enforces valid status values."""
    auth_request_id = uuid.uuid4()

    # Try to create with invalid status (should fail due to check constraint)
    with pytest.raises(Exception):
        await db_conn.execute(
            """
            INSERT INTO auth_request_state (
                auth_request_id, restaurant_id, payment_token,
                status, amount_cents, currency, created_at, updated_at, last_event_sequence
            )
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), 1)
            """,
            auth_request_id,
            test_restaurant_id,
            test_payment_token,
            "INVALID_STATUS",  # This should fail
            1050,
            "USD",
        )
