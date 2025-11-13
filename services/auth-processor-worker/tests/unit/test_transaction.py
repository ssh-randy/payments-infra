"""Unit tests for atomic transaction logic.

These tests verify that events and read model updates are truly atomic.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth_processor_worker.infrastructure import transaction


@pytest.fixture
def mock_connection():
    """Create a mock database connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    conn.fetchrow = AsyncMock()
    return conn


@pytest.fixture
def mock_transaction_context(mock_connection):
    """Create a mock transaction context."""
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=mock_connection)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


class TestAuthAttemptStarted:
    """Tests for recording AuthAttemptStarted events."""

    @pytest.mark.asyncio
    async def test_record_auth_attempt_started_success(
        self, mock_connection, mock_transaction_context
    ):
        """Test successful recording of AuthAttemptStarted event."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"
        metadata = {"worker_id": "worker-1"}

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=2,
            ) as mock_get_seq:
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ) as mock_write_event:
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_processing"
                    ) as mock_update:
                        sequence = await transaction.record_auth_attempt_started(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                            metadata=metadata,
                        )

        assert sequence == 2
        mock_get_seq.assert_called_once_with(mock_connection, auth_request_id)
        mock_write_event.assert_called_once()
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=2,
        )

    @pytest.mark.asyncio
    async def test_record_auth_attempt_started_rollback_on_event_write_failure(
        self, mock_connection, mock_transaction_context
    ):
        """Test that transaction rolls back if event write fails."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=2,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event",
                    side_effect=Exception("Database error"),
                ):
                    with pytest.raises(Exception, match="Database error"):
                        await transaction.record_auth_attempt_started(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                        )

        # Verify transaction context manager was called (implicitly rolls back)
        mock_transaction_context.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_auth_attempt_started_rollback_on_read_model_failure(
        self, mock_connection, mock_transaction_context
    ):
        """Test that transaction rolls back if read model update fails."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=2,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_processing",
                        side_effect=Exception("Read model update failed"),
                    ):
                        with pytest.raises(Exception, match="Read model update failed"):
                            await transaction.record_auth_attempt_started(
                                auth_request_id=auth_request_id,
                                event_data=event_data,
                            )

        # Verify transaction context manager was called (implicitly rolls back)
        mock_transaction_context.__aexit__.assert_called_once()


class TestAuthResponseAuthorized:
    """Tests for recording AuthResponseReceived (AUTHORIZED) events."""

    @pytest.mark.asyncio
    async def test_record_auth_response_authorized_success(
        self, mock_connection, mock_transaction_context
    ):
        """Test successful recording of authorized response."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"
        metadata = {"correlation_id": "test-123"}

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=3,
            ) as mock_get_seq:
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ) as mock_write_event:
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_authorized"
                    ) as mock_update:
                        sequence = await transaction.record_auth_response_authorized(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                            processor_auth_id="ch_123",
                            processor_name="stripe",
                            authorized_amount_cents=1000,
                            authorization_code="ABC123",
                            metadata=metadata,
                        )

        assert sequence == 3
        mock_get_seq.assert_called_once_with(mock_connection, auth_request_id)
        mock_write_event.assert_called_once()
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=3,
            processor_auth_id="ch_123",
            processor_name="stripe",
            authorized_amount_cents=1000,
            authorization_code="ABC123",
        )


class TestAuthResponseDenied:
    """Tests for recording AuthResponseReceived (DENIED) events."""

    @pytest.mark.asyncio
    async def test_record_auth_response_denied_success(
        self, mock_connection, mock_transaction_context
    ):
        """Test successful recording of denied response."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=3,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_denied"
                    ) as mock_update:
                        sequence = await transaction.record_auth_response_denied(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                            processor_name="stripe",
                            denial_code="insufficient_funds",
                            denial_reason="Card has insufficient funds",
                        )

        assert sequence == 3
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=3,
            processor_name="stripe",
            denial_code="insufficient_funds",
            denial_reason="Card has insufficient funds",
        )


class TestAuthAttemptFailed:
    """Tests for recording AuthAttemptFailed events."""

    @pytest.mark.asyncio
    async def test_record_auth_attempt_failed_terminal(
        self, mock_connection, mock_transaction_context
    ):
        """Test recording terminal failure (status becomes FAILED)."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=4,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_failed"
                    ) as mock_update:
                        sequence = await transaction.record_auth_attempt_failed_terminal(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                        )

        assert sequence == 4
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=4,
        )

    @pytest.mark.asyncio
    async def test_record_auth_attempt_failed_retryable(
        self, mock_connection, mock_transaction_context
    ):
        """Test recording retryable failure (status stays PROCESSING)."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=3,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_retry_attempt"
                    ) as mock_update:
                        sequence = (
                            await transaction.record_auth_attempt_failed_retryable(
                                auth_request_id=auth_request_id,
                                event_data=event_data,
                            )
                        )

        assert sequence == 3
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=3,
        )


class TestAuthRequestExpired:
    """Tests for recording AuthRequestExpired events."""

    @pytest.mark.asyncio
    async def test_record_auth_request_expired_success(
        self, mock_connection, mock_transaction_context
    ):
        """Test successful recording of expired request."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                return_value=2,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_expired"
                    ) as mock_update:
                        sequence = await transaction.record_auth_request_expired(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                        )

        assert sequence == 2
        mock_update.assert_called_once_with(
            conn=mock_connection,
            auth_request_id=auth_request_id,
            sequence_number=2,
        )


class TestTransactionAtomicity:
    """Tests to verify transaction atomicity guarantees."""

    @pytest.mark.asyncio
    async def test_sequence_number_fetched_within_transaction(
        self, mock_connection, mock_transaction_context
    ):
        """Verify sequence number is fetched within the transaction context."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        sequence_fetch_order = []

        async def track_sequence_fetch(conn, agg_id):
            sequence_fetch_order.append("sequence_fetched")
            return 5

        mock_transaction_context.__aenter__ = AsyncMock(
            side_effect=lambda: (
                sequence_fetch_order.append("transaction_started"),
                mock_connection,
            )[1]
        )

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                side_effect=track_sequence_fetch,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event"
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_processing"
                    ):
                        await transaction.record_auth_attempt_started(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                        )

        # Verify sequence was fetched after transaction started
        assert sequence_fetch_order == ["transaction_started", "sequence_fetched"]

    @pytest.mark.asyncio
    async def test_all_operations_use_same_connection(
        self, mock_connection, mock_transaction_context
    ):
        """Verify all operations use the same connection from transaction context."""
        auth_request_id = uuid.uuid4()
        event_data = b"test_event_data"

        connections_used = []

        async def track_connection_get_seq(conn, agg_id):
            connections_used.append(("get_seq", id(conn)))
            return 2

        async def track_connection_write_event(conn, **kwargs):
            connections_used.append(("write_event", id(conn)))

        async def track_connection_update(conn, **kwargs):
            connections_used.append(("update_read_model", id(conn)))

        with patch(
            "auth_processor_worker.infrastructure.transaction.database.transaction",
            return_value=mock_transaction_context,
        ):
            with patch(
                "auth_processor_worker.infrastructure.transaction.event_store.get_next_sequence_number",
                side_effect=track_connection_get_seq,
            ):
                with patch(
                    "auth_processor_worker.infrastructure.transaction.event_store.write_event",
                    side_effect=track_connection_write_event,
                ):
                    with patch(
                        "auth_processor_worker.infrastructure.transaction.read_model.update_to_processing",
                        side_effect=track_connection_update,
                    ):
                        await transaction.record_auth_attempt_started(
                            auth_request_id=auth_request_id,
                            event_data=event_data,
                        )

        # Verify all operations used the same connection
        conn_ids = [conn_id for _, conn_id in connections_used]
        assert len(set(conn_ids)) == 1, "All operations must use same connection"
        assert len(connections_used) == 3, "All three operations should have been called"
