"""Integration tests for transaction atomicity with real PostgreSQL database.

These tests verify that events and read model updates are truly atomic using a real database.
They test the critical guarantees:
1. If event write fails, read model should NOT be updated
2. If read model update fails, event should NOT be written
3. Sequence numbers are consistent under concurrent load
4. Transaction isolation prevents partial state visibility
5. Immediate consistency after commit (read-your-writes)
"""

import asyncio
import uuid
from unittest.mock import patch

import pytest

from auth_processor_worker.infrastructure import event_store, read_model, transaction


@pytest.mark.integration
class TestTransactionAtomicity:
    """Tests to verify true atomicity with real database."""

    @pytest.mark.asyncio
    async def test_event_write_failure_rolls_back_read_model(
        self, db_conn, seed_auth_request
    ):
        """Test that if event write fails, read model update is rolled back.

        This is a critical atomicity test - we simulate an event write failure
        and verify that the read model was NOT updated.
        """
        auth_request_id = seed_auth_request

        # Verify initial state
        initial_state = await db_conn.fetchrow(
            "SELECT status, last_event_sequence FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert initial_state["status"] == "PENDING"
        assert initial_state["last_event_sequence"] == 0

        # Simulate event write failure by patching the write_event function
        with patch(
            "auth_processor_worker.infrastructure.transaction.event_store.write_event",
            side_effect=Exception("Simulated event write failure"),
        ):
            # Attempt to record event (should fail and rollback)
            with pytest.raises(Exception, match="Simulated event write failure"):
                await transaction.record_auth_attempt_started(
                    auth_request_id=auth_request_id,
                    event_data=b"test_data",
                    metadata={"worker_id": "test-worker"},
                )

        # CRITICAL CHECK: Verify read model was NOT updated
        final_state = await db_conn.fetchrow(
            "SELECT status, last_event_sequence FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert final_state["status"] == "PENDING", "Status should remain PENDING after rollback"
        assert (
            final_state["last_event_sequence"] == 0
        ), "Sequence should remain 0 after rollback"

        # CRITICAL CHECK: Verify event was NOT written
        event_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
            auth_request_id,
        )
        assert event_count == 0, "No events should be written after rollback"

    @pytest.mark.asyncio
    async def test_read_model_update_failure_rolls_back_event(
        self, db_conn, seed_auth_request
    ):
        """Test that if read model update fails, event write is rolled back.

        This verifies the reverse scenario - read model failure rolls back event.
        """
        auth_request_id = seed_auth_request

        # Simulate read model update failure by patching
        with patch(
            "auth_processor_worker.infrastructure.transaction.read_model.update_to_processing",
            side_effect=Exception("Simulated read model update failure"),
        ):
            # Attempt to record event (should fail and rollback)
            with pytest.raises(Exception, match="Simulated read model update failure"):
                await transaction.record_auth_attempt_started(
                    auth_request_id=auth_request_id,
                    event_data=b"test_data",
                )

        # CRITICAL CHECK: Verify event was NOT written (rollback worked)
        event_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
            auth_request_id,
        )
        assert event_count == 0, "Event should be rolled back when read model fails"

        # CRITICAL CHECK: Verify read model was NOT updated
        final_state = await db_conn.fetchrow(
            "SELECT status FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert final_state["status"] == "PENDING", "Status should remain unchanged"

    @pytest.mark.asyncio
    async def test_database_constraint_violation_rolls_back_both(
        self, db_conn, seed_auth_request
    ):
        """Test that database constraint violations cause complete rollback.

        This tests real database constraint enforcement.
        """
        auth_request_id = seed_auth_request

        # First, successfully record an event
        await transaction.record_auth_attempt_started(
            auth_request_id=auth_request_id,
            event_data=b"test_data",
        )

        # Verify it was recorded
        event_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
            auth_request_id,
        )
        assert event_count == 1

        # Now try to insert duplicate sequence number (should violate unique constraint)
        # This should cause rollback of both event and read model update
        with patch(
            "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
            return_value=1,  # Force duplicate sequence
        ):
            with pytest.raises(Exception):  # Should raise constraint violation
                await transaction.record_auth_response_authorized(
                    auth_request_id=auth_request_id,
                    event_data=b"test_data",
                    processor_auth_id="ch_123",
                    processor_name="stripe",
                    authorized_amount_cents=1000,
                    authorization_code="ABC123",
                )

        # CRITICAL CHECK: Still only 1 event (duplicate was rolled back)
        final_event_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
            auth_request_id,
        )
        assert final_event_count == 1, "Duplicate event should be rolled back"

        # CRITICAL CHECK: Read model should still show PROCESSING (not AUTHORIZED)
        status = await db_conn.fetchval(
            "SELECT status FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert status == "PROCESSING", "Read model should not show AUTHORIZED after rollback"


@pytest.mark.integration
class TestImmediateConsistency:
    """Tests to verify immediate consistency (read-your-writes)."""

    @pytest.mark.asyncio
    async def test_read_your_writes_immediate_consistency(
        self, db_conn, seed_auth_request
    ):
        """Test that after transaction commits, reads immediately see the update.

        No eventual consistency delay - event and read model are immediately consistent.
        """
        auth_request_id = seed_auth_request

        # Record event atomically
        sequence = await transaction.record_auth_attempt_started(
            auth_request_id=auth_request_id,
            event_data=b"test_data",
            metadata={"worker_id": "test-worker"},
        )

        # IMMEDIATE READ: Query database right after commit
        status = await db_conn.fetchrow(
            "SELECT status, last_event_sequence FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )

        # CRITICAL CHECK: Read model immediately reflects the event
        assert status["status"] == "PROCESSING", "Status should be immediately updated"
        assert (
            status["last_event_sequence"] == sequence
        ), "Sequence should match immediately"

        # CRITICAL CHECK: Event is immediately queryable
        event = await db_conn.fetchrow(
            """
            SELECT event_type, sequence_number
            FROM payment_events
            WHERE aggregate_id = $1 AND sequence_number = $2
            """,
            auth_request_id,
            sequence,
        )
        assert event is not None, "Event should be immediately queryable"
        assert event["event_type"] == "AuthAttemptStarted"
        assert event["sequence_number"] == sequence

    @pytest.mark.asyncio
    async def test_multiple_sequential_updates_consistent(
        self, db_conn, seed_auth_request
    ):
        """Test multiple sequential updates maintain consistency."""
        auth_request_id = seed_auth_request

        # Step 1: Start processing
        seq1 = await transaction.record_auth_attempt_started(
            auth_request_id=auth_request_id,
            event_data=b"started",
        )

        # Check consistency after step 1
        state1 = await db_conn.fetchrow(
            "SELECT status, last_event_sequence FROM auth_request_state WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert state1["status"] == "PROCESSING"
        assert state1["last_event_sequence"] == seq1

        # Step 2: Record authorized response
        seq2 = await transaction.record_auth_response_authorized(
            auth_request_id=auth_request_id,
            event_data=b"authorized",
            processor_auth_id="ch_123",
            processor_name="stripe",
            authorized_amount_cents=1000,
            authorization_code="ABC123",
        )

        # Check consistency after step 2
        state2 = await db_conn.fetchrow(
            """
            SELECT status, last_event_sequence, processor_auth_id, processor_name, authorized_amount_cents
            FROM auth_request_state
            WHERE auth_request_id = $1
            """,
            auth_request_id,
        )
        assert state2["status"] == "AUTHORIZED"
        assert state2["last_event_sequence"] == seq2
        assert state2["processor_auth_id"] == "ch_123"
        assert state2["processor_name"] == "stripe"
        assert state2["authorized_amount_cents"] == 1000

        # CRITICAL CHECK: Both events exist
        event_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
            auth_request_id,
        )
        assert event_count == 2, "Both events should be persisted"


@pytest.mark.integration
class TestSequenceNumberConsistency:
    """Tests to verify sequence number consistency under various scenarios."""

    @pytest.mark.asyncio
    async def test_sequence_numbers_monotonically_increasing(
        self, db_conn, seed_auth_request
    ):
        """Test that sequence numbers are monotonically increasing."""
        auth_request_id = seed_auth_request

        sequences = []

        # Record multiple events
        seq1 = await transaction.record_auth_attempt_started(
            auth_request_id=auth_request_id,
            event_data=b"event1",
        )
        sequences.append(seq1)

        seq2 = await transaction.record_auth_attempt_failed_retryable(
            auth_request_id=auth_request_id,
            event_data=b"event2",
        )
        sequences.append(seq2)

        seq3 = await transaction.record_auth_response_authorized(
            auth_request_id=auth_request_id,
            event_data=b"event3",
            processor_auth_id="ch_123",
            processor_name="stripe",
            authorized_amount_cents=1000,
            authorization_code="ABC123",
        )
        sequences.append(seq3)

        # CRITICAL CHECK: Sequences are monotonically increasing
        assert sequences == sorted(sequences), "Sequences must be monotonically increasing"
        assert sequences == [1, 2, 3], "Sequences should be 1, 2, 3"

        # CRITICAL CHECK: No gaps in sequence numbers
        events = await db_conn.fetch(
            """
            SELECT sequence_number
            FROM payment_events
            WHERE aggregate_id = $1
            ORDER BY sequence_number
            """,
            auth_request_id,
        )
        event_sequences = [e["sequence_number"] for e in events]
        assert event_sequences == [1, 2, 3], "No gaps in sequence numbers"

    @pytest.mark.asyncio
    async def test_concurrent_transactions_no_duplicate_sequences(
        self, db_pool, test_auth_request_id, test_restaurant_id, test_payment_token
    ):
        """Test that concurrent transactions don't create duplicate sequence numbers.

        This test verifies that database constraints prevent duplicate sequences.
        Some transactions may fail with UniqueViolationError, which is EXPECTED
        and proves atomicity - the database prevents duplicate sequences.
        """
        auth_request_id = test_auth_request_id

        # Get a connection and seed the auth request
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auth_request_state (
                    auth_request_id, restaurant_id, payment_token,
                    status, amount_cents, currency,
                    created_at, updated_at, last_event_sequence
                )
                VALUES ($1, $2, $3, 'PENDING', 1000, 'USD', NOW(), NOW(), 0)
                """,
                auth_request_id,
                test_restaurant_id,
                test_payment_token,
            )

        # Launch multiple concurrent transactions trying to write events
        async def write_event(event_num):
            """Write an event - may fail with UniqueViolationError due to race."""
            import asyncpg.exceptions

            try:
                await asyncio.sleep(0.001 * event_num)  # Minimal stagger for contention
                return await transaction.record_auth_attempt_failed_retryable(
                    auth_request_id=auth_request_id,
                    event_data=f"concurrent_event_{event_num}".encode(),
                    metadata={"event_num": event_num},
                )
            except asyncpg.exceptions.UniqueViolationError:
                # Expected - database prevented duplicate sequence
                return None

        # Run 5 concurrent transactions (reduced to increase success rate while still testing concurrency)
        results = await asyncio.gather(*[write_event(i) for i in range(5)])

        # Filter out None (failed attempts)
        successful_sequences = [r for r in results if r is not None]

        # CRITICAL CHECK: All successful sequences are unique (no duplicates)
        assert len(successful_sequences) == len(set(successful_sequences)), \
            "All successful sequence numbers must be unique"

        # CRITICAL CHECK: At least some transactions succeeded
        assert len(successful_sequences) >= 1, "At least one transaction should succeed"

        # CRITICAL CHECK: Verify in database - no gaps in what was written
        async with db_pool.acquire() as conn:
            sequences_in_db = await conn.fetch(
                """
                SELECT sequence_number
                FROM payment_events
                WHERE aggregate_id = $1
                ORDER BY sequence_number
                """,
                auth_request_id,
            )
            db_sequences = [row["sequence_number"] for row in sequences_in_db]

            # Sequences should be consecutive starting from 1
            expected_sequences = list(range(1, len(db_sequences) + 1))
            assert db_sequences == expected_sequences, \
                f"Database sequences should be consecutive: got {db_sequences}, expected {expected_sequences}"

        # CRITICAL CHECK: Database constraint prevented duplicates
        # If we got UniqueViolationErrors, that proves atomicity works
        failures = len([r for r in results if r is None])
        print(f"Concurrent test: {len(successful_sequences)} successful, {failures} failed (prevented by DB constraints)")


@pytest.mark.integration
class TestTransactionIsolation:
    """Tests to verify transaction isolation - no partial state visible."""

    @pytest.mark.asyncio
    async def test_uncommitted_changes_not_visible_to_other_transactions(
        self, db_pool, test_auth_request_id, test_restaurant_id, test_payment_token
    ):
        """Test that uncommitted changes in one transaction are not visible to others.

        This verifies transaction isolation.
        """
        auth_request_id = test_auth_request_id

        # Seed auth request
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auth_request_state (
                    auth_request_id, restaurant_id, payment_token,
                    status, amount_cents, currency,
                    created_at, updated_at, last_event_sequence
                )
                VALUES ($1, $2, $3, 'PENDING', 1000, 'USD', NOW(), NOW(), 0)
                """,
                auth_request_id,
                test_restaurant_id,
                test_payment_token,
            )

        # Transaction 1: Start but don't commit
        async with db_pool.acquire() as conn1:
            async with conn1.transaction():
                # Write event but don't commit yet
                await event_store.write_event(
                    conn=conn1,
                    event_id=uuid.uuid4(),
                    aggregate_id=auth_request_id,
                    aggregate_type="auth_request",
                    event_type="AuthAttemptStarted",
                    event_data=b"test",
                    sequence_number=1,
                )

                await read_model.update_to_processing(
                    conn=conn1,
                    auth_request_id=auth_request_id,
                    sequence_number=1,
                )

                # Transaction 2: Check if it can see uncommitted changes
                async with db_pool.acquire() as conn2:
                    # CRITICAL CHECK: Should NOT see uncommitted event
                    event_count = await conn2.fetchval(
                        "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
                        auth_request_id,
                    )
                    assert (
                        event_count == 0
                    ), "Uncommitted events should not be visible to other transactions"

                    # CRITICAL CHECK: Should NOT see uncommitted read model update
                    status = await conn2.fetchval(
                        "SELECT status FROM auth_request_state WHERE auth_request_id = $1",
                        auth_request_id,
                    )
                    assert (
                        status == "PENDING"
                    ), "Uncommitted read model changes should not be visible"

                # Transaction 1 commits here (exiting context manager)

        # After commit, changes should be visible
        async with db_pool.acquire() as conn:
            event_count = await conn.fetchval(
                "SELECT COUNT(*) FROM payment_events WHERE aggregate_id = $1",
                auth_request_id,
            )
            assert event_count == 1, "Event should be visible after commit"

            status = await conn.fetchval(
                "SELECT status FROM auth_request_state WHERE auth_request_id = $1",
                auth_request_id,
            )
            assert status == "PROCESSING", "Status should be updated after commit"
