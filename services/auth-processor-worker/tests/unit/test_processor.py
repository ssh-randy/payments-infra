"""Unit tests for auth request processor orchestration."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth_processor_worker.handlers.processor import ProcessingResult, process_auth_request
from auth_processor_worker.models.authorization import AuthStatus, AuthorizationResult, PaymentData
from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)


@pytest.fixture
def auth_request_id():
    """Test auth request ID."""
    return uuid.uuid4()


@pytest.fixture
def worker_id():
    """Test worker ID."""
    return "test-worker-123"


@pytest.fixture
def auth_details():
    """Mock auth request details."""
    return {
        "auth_request_id": uuid.uuid4(),
        "restaurant_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "payment_token": "pt_test123",
        "status": "PENDING",
        "amount_cents": 10000,
        "currency": "usd",
        "metadata": {},
        "created_at": datetime.utcnow(),
        "last_event_sequence": 0,
    }


@pytest.fixture
def restaurant_config():
    """Mock restaurant config."""
    return {
        "restaurant_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "config_version": "v1",
        "processor_name": "stripe",
        "processor_config": {"api_key": "sk_test_123"},
        "is_active": True,
    }


@pytest.fixture
def payment_data():
    """Mock payment data."""
    return PaymentData(
        card_number="4242424242424242",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        cardholder_name="Test User",
        billing_zip="12345",
    )


@pytest.fixture
def authorized_result():
    """Mock authorized result."""
    return AuthorizationResult(
        status=AuthStatus.AUTHORIZED,
        processor_name="stripe",
        processor_auth_id="ch_test123",
        authorization_code="auth_123",
        authorized_amount_cents=10000,
        currency="usd",
        authorized_at=datetime.utcnow(),
    )


@pytest.fixture
def denied_result():
    """Mock denied result."""
    return AuthorizationResult(
        status=AuthStatus.DENIED,
        processor_name="stripe",
        denial_code="insufficient_funds",
        denial_reason="Insufficient funds",
    )


@pytest.mark.asyncio
class TestProcessAuthRequestHappyPath:
    """Tests for successful processing scenarios."""

    async def test_authorized_success(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
        payment_data,
        authorized_result,
    ):
        """Test successful authorization flow."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt, \
             patch("auth_processor_worker.handlers.processor.get_processor") as mock_get_processor:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_transaction.record_auth_response_authorized = AsyncMock(return_value=2)

            mock_decrypt.return_value = payment_data

            mock_processor = AsyncMock()
            mock_processor.authorize = AsyncMock(return_value=authorized_result)
            mock_get_processor.return_value = mock_processor

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.SUCCESS

            # Verify lock was acquired and released
            mock_locking.acquire_lock.assert_called_once()
            mock_locking.release_lock.assert_called_once()

            # Verify void check
            mock_event_store.check_for_void_event.assert_called_once()

            # Verify attempt started was recorded
            mock_transaction.record_auth_attempt_started.assert_called_once()

            # Verify auth details and config were fetched
            mock_read_model.get_auth_request_details.assert_called_once()
            mock_read_model.get_restaurant_config.assert_called_once()

            # Verify token was decrypted
            mock_decrypt.assert_called_once()

            # Verify processor was called
            mock_processor.authorize.assert_called_once()

            # Verify authorized response was recorded
            mock_transaction.record_auth_response_authorized.assert_called_once()

    async def test_denied_success(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
        payment_data,
        denied_result,
    ):
        """Test successful denial flow (not a failure)."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt, \
             patch("auth_processor_worker.handlers.processor.get_processor") as mock_get_processor:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_transaction.record_auth_response_denied = AsyncMock(return_value=2)

            mock_decrypt.return_value = payment_data

            mock_processor = AsyncMock()
            mock_processor.authorize = AsyncMock(return_value=denied_result)
            mock_get_processor.return_value = mock_processor

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.SUCCESS

            # Verify denied response was recorded
            mock_transaction.record_auth_response_denied.assert_called_once()

            # Verify lock was released
            mock_locking.release_lock.assert_called_once()


@pytest.mark.asyncio
class TestProcessAuthRequestLockScenarios:
    """Tests for lock acquisition scenarios."""

    async def test_lock_not_acquired(self, auth_request_id, worker_id):
        """Test skipping when lock cannot be acquired."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking:
            mock_locking.acquire_lock = AsyncMock(return_value=False)

            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            assert result == ProcessingResult.SKIPPED_LOCK_NOT_ACQUIRED
            mock_locking.acquire_lock.assert_called_once()


@pytest.mark.asyncio
class TestProcessAuthRequestVoidDetection:
    """Tests for void detection scenarios."""

    async def test_void_detected(self, auth_request_id, worker_id):
        """Test void detection before processing."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=True)
            mock_transaction.record_auth_request_expired = AsyncMock(return_value=1)

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.SKIPPED_VOID_DETECTED

            # Verify expired event was recorded
            mock_transaction.record_auth_request_expired.assert_called_once()

            # Verify lock was released
            mock_locking.release_lock.assert_called_once()


@pytest.mark.asyncio
class TestProcessAuthRequestTerminalErrors:
    """Tests for terminal error scenarios."""

    async def test_auth_request_not_found(self, auth_request_id, worker_id):
        """Test terminal failure when auth request not found."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=None)
            mock_transaction.record_auth_attempt_failed_terminal = AsyncMock(return_value=2)

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.TERMINAL_FAILURE
            mock_transaction.record_auth_attempt_failed_terminal.assert_called_once()
            mock_locking.release_lock.assert_called_once()

    async def test_restaurant_config_not_found(
        self,
        auth_request_id,
        worker_id,
        auth_details,
    ):
        """Test terminal failure when restaurant config not found."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=None)
            mock_transaction.record_auth_attempt_failed_terminal = AsyncMock(return_value=2)

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.TERMINAL_FAILURE
            mock_transaction.record_auth_attempt_failed_terminal.assert_called_once()
            mock_locking.release_lock.assert_called_once()

    @pytest.mark.parametrize("exception_class", [TokenNotFound, TokenExpired, Forbidden])
    async def test_token_service_terminal_errors(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
        exception_class,
    ):
        """Test terminal errors from token service."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            # Token service raises terminal error
            mock_decrypt.side_effect = exception_class("Terminal error")
            mock_transaction.record_auth_attempt_failed_terminal = AsyncMock(return_value=2)

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.TERMINAL_FAILURE
            mock_transaction.record_auth_attempt_failed_terminal.assert_called_once()
            mock_locking.release_lock.assert_called_once()


@pytest.mark.asyncio
class TestProcessAuthRequestRetryableErrors:
    """Tests for retryable error scenarios."""

    async def test_token_service_timeout_retryable(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
    ):
        """Test retryable error from token service timeout."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            # Token service times out (retryable)
            mock_decrypt.side_effect = ProcessorTimeout("Service unavailable")
            mock_transaction.record_auth_attempt_failed_retryable = AsyncMock(return_value=2)

            # Execute (receive_count=1, below max_retries=5)
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.RETRYABLE_FAILURE
            mock_transaction.record_auth_attempt_failed_retryable.assert_called_once()
            mock_locking.release_lock.assert_called_once()

    async def test_token_service_timeout_max_retries_exceeded(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
    ):
        """Test terminal failure when max retries exceeded on token service timeout."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            # Token service times out
            mock_decrypt.side_effect = ProcessorTimeout("Service unavailable")
            mock_transaction.record_auth_attempt_failed_terminal = AsyncMock(return_value=2)

            # Execute (receive_count=5, at max_retries=5)
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=5,
            )

            # Assert
            assert result == ProcessingResult.TERMINAL_FAILURE
            mock_transaction.record_auth_attempt_failed_terminal.assert_called_once()
            mock_locking.release_lock.assert_called_once()

    async def test_processor_timeout_retryable(
        self,
        auth_request_id,
        worker_id,
        auth_details,
        restaurant_config,
        payment_data,
    ):
        """Test retryable error from processor timeout."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.read_model") as mock_read_model, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction, \
             patch("auth_processor_worker.handlers.processor._decrypt_payment_token") as mock_decrypt, \
             patch("auth_processor_worker.handlers.processor.get_processor") as mock_get_processor:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            mock_event_store.check_for_void_event = AsyncMock(return_value=False)
            mock_transaction.record_auth_attempt_started = AsyncMock(return_value=1)
            mock_read_model.get_auth_request_details = AsyncMock(return_value=auth_details)
            mock_read_model.get_restaurant_config = AsyncMock(return_value=restaurant_config)

            mock_decrypt.return_value = payment_data

            # Processor times out (retryable)
            mock_processor = AsyncMock()
            mock_processor.authorize = AsyncMock(side_effect=ProcessorTimeout("Stripe unavailable"))
            mock_get_processor.return_value = mock_processor

            mock_transaction.record_auth_attempt_failed_retryable = AsyncMock(return_value=2)

            # Execute (receive_count=1, below max_retries=5)
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.RETRYABLE_FAILURE
            mock_transaction.record_auth_attempt_failed_retryable.assert_called_once()
            mock_locking.release_lock.assert_called_once()


@pytest.mark.asyncio
class TestProcessAuthRequestLockCleanup:
    """Tests for lock cleanup in error scenarios."""

    async def test_lock_released_on_unexpected_error(self, auth_request_id, worker_id):
        """Test that lock is always released even on unexpected errors."""
        with patch("auth_processor_worker.handlers.processor.locking") as mock_locking, \
             patch("auth_processor_worker.handlers.processor.database") as mock_database, \
             patch("auth_processor_worker.handlers.processor.event_store") as mock_event_store, \
             patch("auth_processor_worker.handlers.processor.transaction") as mock_transaction:

            # Setup mocks
            mock_locking.acquire_lock = AsyncMock(return_value=True)
            mock_locking.release_lock = AsyncMock()

            mock_conn = AsyncMock()
            mock_database.get_connection.return_value.__aenter__.return_value = mock_conn

            # Unexpected error during void check
            mock_event_store.check_for_void_event = AsyncMock(
                side_effect=Exception("Unexpected database error")
            )
            mock_transaction.record_auth_attempt_failed_terminal = AsyncMock(return_value=1)

            # Execute
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=worker_id,
                receive_count=1,
            )

            # Assert
            assert result == ProcessingResult.TERMINAL_FAILURE

            # Verify lock was still released despite error
            mock_locking.release_lock.assert_called_once()
