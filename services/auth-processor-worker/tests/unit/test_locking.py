"""Unit tests for distributed locking mechanism."""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth_processor_worker.infrastructure.locking import (
    acquire_lock,
    release_lock,
    cleanup_expired_locks,
    start_lock_cleanup_task,
)


@pytest.fixture
def auth_request_id():
    """Generate a test auth request ID."""
    return uuid.uuid4()


@pytest.fixture
def worker_id():
    """Generate a test worker ID."""
    return "test-worker-123"


class TestAcquireLock:
    """Test cases for acquire_lock function."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, auth_request_id, worker_id):
        """Test successfully acquiring a lock."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"auth_request_id": auth_request_id}

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            result = await acquire_lock(auth_request_id, worker_id)

            assert result is True
            mock_conn.fetchrow.assert_called_once()
            call_args = mock_conn.fetchrow.call_args[0]
            assert auth_request_id in call_args
            assert worker_id in call_args
            assert 30 in call_args  # Default TTL

    @pytest.mark.asyncio
    async def test_acquire_lock_with_custom_ttl(self, auth_request_id, worker_id):
        """Test acquiring a lock with custom TTL."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"auth_request_id": auth_request_id}

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            result = await acquire_lock(auth_request_id, worker_id, ttl_seconds=60)

            assert result is True
            call_args = mock_conn.fetchrow.call_args[0]
            assert 60 in call_args  # Custom TTL

    @pytest.mark.asyncio
    async def test_acquire_lock_already_held(self, auth_request_id, worker_id):
        """Test attempting to acquire a lock that's already held."""
        mock_conn = AsyncMock()
        # First call returns None (conflict, lock not acquired)
        # Second call returns existing lock info
        mock_conn.fetchrow.side_effect = [
            None,  # INSERT returned nothing (conflict)
            {
                "worker_id": "other-worker-456",
                "expires_at": datetime.now() + timedelta(seconds=30),
            },
        ]

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            result = await acquire_lock(auth_request_id, worker_id)

            assert result is False
            assert mock_conn.fetchrow.call_count == 2

    @pytest.mark.asyncio
    async def test_acquire_lock_race_condition(self, auth_request_id):
        """Test race condition between two workers attempting to acquire same lock."""
        mock_conn = AsyncMock()

        # Simulate two workers racing: first succeeds, second fails
        call_count = 0

        def mock_fetchrow(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First worker succeeds
                return {"auth_request_id": auth_request_id}
            else:
                # Second worker fails (conflict)
                return None

        mock_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            # First worker acquires lock
            result1 = await acquire_lock(auth_request_id, "worker-1")
            assert result1 is True

            # Reset for second worker attempt
            mock_conn.fetchrow.side_effect = [
                None,  # Conflict on insert
                {"worker_id": "worker-1", "expires_at": datetime.now() + timedelta(seconds=30)},
            ]

            # Second worker fails to acquire lock
            result2 = await acquire_lock(auth_request_id, "worker-2")
            assert result2 is False

    @pytest.mark.asyncio
    async def test_acquire_lock_database_error(self, auth_request_id, worker_id):
        """Test handling of database errors during lock acquisition."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = Exception("Database connection failed")

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            with pytest.raises(Exception, match="Database connection failed"):
                await acquire_lock(auth_request_id, worker_id)


class TestReleaseLock:
    """Test cases for release_lock function."""

    @pytest.mark.asyncio
    async def test_release_lock_success(self, auth_request_id, worker_id):
        """Test successfully releasing a lock."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "DELETE 1"

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            await release_lock(auth_request_id, worker_id)

            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args[0]
            assert auth_request_id in call_args
            assert worker_id in call_args

    @pytest.mark.asyncio
    async def test_release_lock_not_found(self, auth_request_id, worker_id):
        """Test releasing a lock that doesn't exist (already released or expired)."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "DELETE 0"

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            # Should not raise an error, just log a warning
            await release_lock(auth_request_id, worker_id)

            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lock_wrong_worker(self, auth_request_id):
        """Test that only the worker that acquired the lock can release it."""
        mock_conn = AsyncMock()
        # Different worker tries to release - no rows deleted
        mock_conn.execute.return_value = "DELETE 0"

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            await release_lock(auth_request_id, "wrong-worker")

            # Verify the query checked both auth_request_id AND worker_id
            call_args = mock_conn.execute.call_args[0]
            assert auth_request_id in call_args
            assert "wrong-worker" in call_args

    @pytest.mark.asyncio
    async def test_release_lock_database_error(self, auth_request_id, worker_id):
        """Test handling of database errors during lock release."""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database connection failed")

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            with pytest.raises(Exception, match="Database connection failed"):
                await release_lock(auth_request_id, worker_id)


class TestCleanupExpiredLocks:
    """Test cases for cleanup_expired_locks function."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_locks_success(self):
        """Test successful cleanup of expired locks."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "DELETE 3"

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            count = await cleanup_expired_locks()

            assert count == 3
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_locks(self):
        """Test cleanup when there are no expired locks."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "DELETE 0"

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            count = await cleanup_expired_locks()

            assert count == 0
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_database_error(self):
        """Test handling of database errors during cleanup."""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("Database connection failed")

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            with pytest.raises(Exception, match="Database connection failed"):
                await cleanup_expired_locks()


class TestLockCleanupTask:
    """Test cases for start_lock_cleanup_task background task."""

    @pytest.mark.asyncio
    async def test_cleanup_task_runs_periodically(self):
        """Test that cleanup task runs periodically."""
        stop_event = asyncio.Event()
        cleanup_call_count = 0

        async def mock_cleanup():
            nonlocal cleanup_call_count
            cleanup_call_count += 1
            if cleanup_call_count >= 3:
                # Stop after 3 iterations
                stop_event.set()
            return 0

        with patch("auth_processor_worker.infrastructure.locking.cleanup_expired_locks", side_effect=mock_cleanup):
            # Run with very short interval for testing
            await start_lock_cleanup_task(interval_seconds=0.1, stop_event=stop_event)

            # Should have run at least 3 times
            assert cleanup_call_count >= 3

    @pytest.mark.asyncio
    async def test_cleanup_task_stops_on_event(self):
        """Test that cleanup task stops when stop_event is set."""
        stop_event = asyncio.Event()

        with patch("auth_processor_worker.infrastructure.locking.cleanup_expired_locks") as mock_cleanup:
            mock_cleanup.return_value = 0

            # Start task and set stop event after short delay
            async def set_stop_after_delay():
                await asyncio.sleep(0.05)
                stop_event.set()

            # Run both tasks concurrently
            await asyncio.gather(
                start_lock_cleanup_task(interval_seconds=1, stop_event=stop_event),
                set_stop_after_delay()
            )

            # Should have run at least once before stopping
            assert mock_cleanup.call_count >= 1

    @pytest.mark.asyncio
    async def test_cleanup_task_continues_on_error(self):
        """Test that cleanup task continues running even if one iteration fails."""
        stop_event = asyncio.Event()
        call_count = 0

        async def mock_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary database error")
            elif call_count >= 2:
                stop_event.set()
            return 0

        with patch("auth_processor_worker.infrastructure.locking.cleanup_expired_locks", side_effect=mock_cleanup):
            await start_lock_cleanup_task(interval_seconds=0.1, stop_event=stop_event)

            # Should have recovered from error and continued
            assert call_count >= 2


class TestLockLifecycle:
    """Integration-style tests for complete lock lifecycle."""

    @pytest.mark.asyncio
    async def test_acquire_and_release_lifecycle(self, auth_request_id, worker_id):
        """Test complete lifecycle of acquiring and releasing a lock."""
        mock_conn = AsyncMock()

        # Track calls to verify lifecycle
        calls = []

        async def track_fetchrow(*args):
            calls.append("acquire")
            return {"auth_request_id": auth_request_id}

        async def track_execute(*args):
            calls.append("release")
            return "DELETE 1"

        mock_conn.fetchrow = track_fetchrow
        mock_conn.execute = track_execute

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            # Acquire lock
            acquired = await acquire_lock(auth_request_id, worker_id)
            assert acquired is True

            # Release lock
            await release_lock(auth_request_id, worker_id)

            # Verify lifecycle
            assert calls == ["acquire", "release"]

    @pytest.mark.asyncio
    async def test_lock_ttl_semantics(self, auth_request_id, worker_id):
        """Test that TTL is properly passed to database."""
        mock_conn = AsyncMock()
        captured_args = None

        async def capture_args(*args):
            nonlocal captured_args
            captured_args = args
            return {"auth_request_id": auth_request_id}

        mock_conn.fetchrow = capture_args

        with patch("auth_processor_worker.infrastructure.locking.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            # Test with custom TTL
            await acquire_lock(auth_request_id, worker_id, ttl_seconds=45)

            # Args are: (sql_query, auth_request_id, worker_id, ttl_seconds)
            assert captured_args is not None
            assert len(captured_args) == 4
            assert captured_args[3] == 45  # TTL is 4th argument
