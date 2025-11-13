"""Integration tests for distributed locking with real PostgreSQL database.

These tests require a running PostgreSQL instance.
Run with: pytest tests/integration/test_locking_integration.py -v -m integration
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from auth_processor_worker.infrastructure.locking import (
    acquire_lock,
    release_lock,
    cleanup_expired_locks,
)


pytestmark = pytest.mark.integration


class TestLockAcquisitionIntegration:
    """Integration tests for lock acquisition with real database."""

    @pytest.mark.asyncio
    async def test_acquire_lock_inserts_row(self, db_conn):
        """Test that acquiring a lock inserts a row in the database."""
        auth_request_id = uuid.uuid4()
        worker_id = "integration-test-worker-1"

        # Acquire lock
        acquired = await acquire_lock(auth_request_id, worker_id)
        assert acquired is True

        # Verify lock exists in database
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )

        assert lock is not None
        assert lock["worker_id"] == worker_id
        assert lock["expires_at"] > datetime.now()

    @pytest.mark.asyncio
    async def test_acquire_lock_with_custom_ttl(self, db_conn):
        """Test that custom TTL is respected."""
        auth_request_id = uuid.uuid4()
        worker_id = "integration-test-worker-2"

        # Acquire lock with 60 second TTL
        acquired = await acquire_lock(auth_request_id, worker_id, ttl_seconds=60)
        assert acquired is True

        # Verify TTL is approximately 60 seconds
        lock = await db_conn.fetchrow(
            "SELECT expires_at, locked_at FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )

        ttl = (lock["expires_at"] - lock["locked_at"]).total_seconds()
        assert 59 <= ttl <= 61  # Allow 1 second margin

    @pytest.mark.asyncio
    async def test_second_worker_cannot_acquire_same_lock(self, db_conn):
        """Test that only one worker can hold a lock at a time."""
        auth_request_id = uuid.uuid4()

        # First worker acquires lock
        acquired1 = await acquire_lock(auth_request_id, "worker-1")
        assert acquired1 is True

        # Second worker tries to acquire same lock
        acquired2 = await acquire_lock(auth_request_id, "worker-2")
        assert acquired2 is False

        # Verify only one lock exists
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert count == 1

        # Verify it's held by first worker
        lock = await db_conn.fetchrow(
            "SELECT worker_id FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock["worker_id"] == "worker-1"

    @pytest.mark.asyncio
    async def test_concurrent_lock_acquisition_race_condition(self, db_conn):
        """Test that concurrent workers racing for the same lock results in exactly one winner."""
        auth_request_id = uuid.uuid4()
        results = []

        async def try_acquire(worker_id: str):
            acquired = await acquire_lock(auth_request_id, worker_id)
            results.append((worker_id, acquired))

        # 5 workers all try to acquire the same lock concurrently
        await asyncio.gather(*[
            try_acquire(f"worker-{i}") for i in range(5)
        ])

        # Exactly one worker should have succeeded
        successful_acquisitions = [r for r in results if r[1] is True]
        failed_acquisitions = [r for r in results if r[1] is False]

        assert len(successful_acquisitions) == 1
        assert len(failed_acquisitions) == 4

        # Verify database state
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert count == 1


class TestLockReleaseIntegration:
    """Integration tests for lock release with real database."""

    @pytest.mark.asyncio
    async def test_release_lock_deletes_row(self, db_conn):
        """Test that releasing a lock deletes the row from database."""
        auth_request_id = uuid.uuid4()
        worker_id = "integration-test-worker-3"

        # Acquire and then release
        await acquire_lock(auth_request_id, worker_id)
        await release_lock(auth_request_id, worker_id)

        # Verify lock is gone
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is None

    @pytest.mark.asyncio
    async def test_only_lock_holder_can_release(self, db_conn):
        """Test that only the worker that acquired the lock can release it."""
        auth_request_id = uuid.uuid4()

        # Worker 1 acquires lock
        await acquire_lock(auth_request_id, "worker-1")

        # Worker 2 tries to release it
        await release_lock(auth_request_id, "worker-2")

        # Lock should still exist (held by worker-1)
        lock = await db_conn.fetchrow(
            "SELECT worker_id FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is not None
        assert lock["worker_id"] == "worker-1"

        # Worker 1 releases it
        await release_lock(auth_request_id, "worker-1")

        # Now lock should be gone
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is None

    @pytest.mark.asyncio
    async def test_release_nonexistent_lock_succeeds(self, db_conn):
        """Test that releasing a nonexistent lock doesn't raise an error."""
        auth_request_id = uuid.uuid4()

        # Should not raise an error
        await release_lock(auth_request_id, "worker-1")


class TestLockCleanupIntegration:
    """Integration tests for expired lock cleanup with real database."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_locks(self, db_conn):
        """Test that cleanup removes expired locks."""
        auth_request_id = uuid.uuid4()
        worker_id = "integration-test-worker-4"

        # Insert an expired lock directly into database
        await db_conn.execute(
            """
            INSERT INTO auth_processing_locks (auth_request_id, worker_id, locked_at, expires_at)
            VALUES ($1, $2, NOW() - INTERVAL '5 minutes', NOW() - INTERVAL '1 minute')
            """,
            auth_request_id,
            worker_id,
        )

        # Run cleanup
        count = await cleanup_expired_locks()

        # Should have cleaned up 1 lock
        assert count == 1

        # Verify lock is gone
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_locks(self, db_conn):
        """Test that cleanup doesn't remove active locks."""
        auth_request_id = uuid.uuid4()
        worker_id = "integration-test-worker-5"

        # Acquire a fresh lock
        await acquire_lock(auth_request_id, worker_id)

        # Run cleanup
        count = await cleanup_expired_locks()

        # Should have cleaned up 0 locks
        assert count == 0

        # Verify lock still exists
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is not None
        assert lock["worker_id"] == worker_id

    @pytest.mark.asyncio
    async def test_cleanup_multiple_expired_locks(self, db_conn):
        """Test cleanup of multiple expired locks."""
        # Insert 3 expired locks
        for i in range(3):
            await db_conn.execute(
                """
                INSERT INTO auth_processing_locks (auth_request_id, worker_id, locked_at, expires_at)
                VALUES ($1, $2, NOW() - INTERVAL '5 minutes', NOW() - INTERVAL '1 minute')
                """,
                uuid.uuid4(),
                f"worker-{i}",
            )

        # Run cleanup
        count = await cleanup_expired_locks()

        # Should have cleaned up 3 locks
        assert count == 3

        # Verify all locks are gone
        total = await db_conn.fetchval(
            "SELECT COUNT(*) FROM auth_processing_locks"
        )
        assert total == 0


class TestLockExpiry:
    """Integration tests for lock expiry behavior."""

    @pytest.mark.asyncio
    async def test_expired_lock_can_be_reacquired(self, db_conn):
        """Test that after a lock expires, another worker can acquire it."""
        auth_request_id = uuid.uuid4()

        # Insert an expired lock
        await db_conn.execute(
            """
            INSERT INTO auth_processing_locks (auth_request_id, worker_id, locked_at, expires_at)
            VALUES ($1, $2, NOW() - INTERVAL '1 minute', NOW() - INTERVAL '30 seconds')
            """,
            auth_request_id,
            "old-worker",
        )

        # Clean up expired locks
        await cleanup_expired_locks()

        # New worker should be able to acquire lock
        acquired = await acquire_lock(auth_request_id, "new-worker")
        assert acquired is True

        # Verify new lock
        lock = await db_conn.fetchrow(
            "SELECT worker_id FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock["worker_id"] == "new-worker"


class TestLockLifecycleIntegration:
    """End-to-end integration tests for complete lock lifecycle."""

    @pytest.mark.asyncio
    async def test_complete_lock_lifecycle(self, db_conn):
        """Test complete lifecycle: acquire -> use -> release."""
        auth_request_id = uuid.uuid4()
        worker_id = "lifecycle-worker"

        # 1. Acquire lock
        acquired = await acquire_lock(auth_request_id, worker_id)
        assert acquired is True

        # 2. Verify lock exists
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is not None

        # 3. Simulate work being done
        await asyncio.sleep(0.1)

        # 4. Release lock
        await release_lock(auth_request_id, worker_id)

        # 5. Verify lock is released
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is None

        # 6. Another worker can now acquire it
        acquired2 = await acquire_lock(auth_request_id, "worker-2")
        assert acquired2 is True

    @pytest.mark.asyncio
    async def test_lock_contention_scenario(self, db_conn):
        """Test realistic scenario with multiple workers and lock contention."""
        auth_request_id = uuid.uuid4()
        processed_by = []

        async def worker_process(worker_id: str):
            """Simulate a worker trying to process a request."""
            # Try to acquire lock
            acquired = await acquire_lock(auth_request_id, worker_id, ttl_seconds=2)

            if acquired:
                try:
                    # Simulate processing
                    await asyncio.sleep(0.2)
                    processed_by.append(worker_id)
                finally:
                    # Always release lock
                    await release_lock(auth_request_id, worker_id)
            else:
                # Lock already held, skip processing
                pass

        # 3 workers try to process the same request
        await asyncio.gather(*[
            worker_process(f"worker-{i}") for i in range(3)
        ])

        # Only one worker should have processed it (exactly-once)
        assert len(processed_by) == 1

        # Lock should be released after processing
        lock = await db_conn.fetchrow(
            "SELECT * FROM auth_processing_locks WHERE auth_request_id = $1",
            auth_request_id,
        )
        assert lock is None
