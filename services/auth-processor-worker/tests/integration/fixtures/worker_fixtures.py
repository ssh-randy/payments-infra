"""Worker lifecycle management fixtures for integration testing.

These fixtures provide controlled start/stop of worker instances for testing
end-to-end message processing, concurrency scenarios, and crash recovery.
"""

import asyncio
import uuid
from typing import Any

import pytest
import pytest_asyncio

from auth_processor_worker.config import settings
from auth_processor_worker.handlers.processor import process_auth_request
from auth_processor_worker.infrastructure.sqs_consumer import SQSConsumer


class WorkerTestInstance:
    """
    Test wrapper for a Worker instance that can be started/stopped programmatically.

    This class provides fine-grained control over worker lifecycle for testing,
    including the ability to start multiple workers, simulate crashes, and verify
    processing completion.
    """

    def __init__(
        self,
        queue_url: str,
        worker_id: str | None = None,
        batch_size: int = 1,
        wait_time_seconds: int = 5,  # Shorter for tests
        visibility_timeout: int = 30,
        sqs_client: Any = None,
        payment_token_client: Any = None,
    ):
        """
        Initialize a worker test instance.

        Args:
            queue_url: SQS queue URL to consume from
            worker_id: Unique worker ID (auto-generated if None)
            batch_size: Number of messages to process per batch
            wait_time_seconds: SQS long polling wait time
            visibility_timeout: SQS message visibility timeout
            sqs_client: Pre-configured SQS client (for tests, to avoid event loop conflicts)
            payment_token_client: Optional payment token client to inject (for testing)
        """
        self.queue_url = queue_url
        self.worker_id = worker_id or f"test-worker-{uuid.uuid4().hex[:8]}"
        self.batch_size = batch_size
        self.wait_time_seconds = wait_time_seconds
        self.visibility_timeout = visibility_timeout
        self.sqs_client = sqs_client
        self.payment_token_client = payment_token_client

        self.sqs_consumer: SQSConsumer | None = None
        self.running = False
        self._worker_task: asyncio.Task | None = None
        self._processed_messages: list[dict[str, Any]] = []
        self._processing_errors: list[Exception] = []

    async def _handle_message(self, message_data: dict[str, Any]) -> None:
        """
        Handle a message from SQS (wrapper around the real handler).

        This wrapper tracks processed messages and errors for test verification.

        Args:
            message_data: Message data from SQS consumer
        """
        try:
            auth_request_id_str = message_data["auth_request_id"]
            receive_count = message_data["receive_count"]

            # Convert to UUID
            auth_request_id = uuid.UUID(auth_request_id_str)

            # Call the real processing function
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=self.worker_id,
                receive_count=receive_count,
                payment_token_client=self.payment_token_client,
            )

            # Track successful processing
            self._processed_messages.append({
                "auth_request_id": auth_request_id_str,
                "receive_count": receive_count,
                "result": result,
            })

            # Re-raise for retryable failures to prevent SQS message deletion
            if result == "retryable_failure":
                raise Exception("Retryable failure - message will be retried")

        except Exception as e:
            self._processing_errors.append(e)
            # Re-raise to prevent SQS message deletion
            raise

    async def start(self) -> None:
        """
        Start the worker in the background.

        This method:
        1. Creates an SQS consumer
        2. Starts it in a background asyncio task
        3. Returns immediately (non-blocking)
        """
        if self.running:
            raise RuntimeError("Worker is already running")

        self.running = True
        self._processed_messages.clear()
        self._processing_errors.clear()

        # Create SQS consumer
        self.sqs_consumer = SQSConsumer(
            queue_url=self.queue_url,
            batch_size=self.batch_size,
            wait_time_seconds=self.wait_time_seconds,
            visibility_timeout=self.visibility_timeout,
            aws_region=settings.aws_region,
            aws_endpoint_url=settings.aws_endpoint_url,
            message_handler=self._handle_message,
            sqs_client=self.sqs_client,  # Inject the test client
        )

        # Start consumer in background task
        self._worker_task = asyncio.create_task(self.sqs_consumer.start())

        # Give the worker a moment to initialize
        await asyncio.sleep(0.5)

    async def stop(self, timeout: float = 5.0) -> None:
        """
        Gracefully stop the worker.

        This method:
        1. Signals the worker to stop
        2. Waits for it to finish current processing
        3. Cancels the worker task if it doesn't stop in time

        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)
        """
        if not self.running:
            return

        self.running = False

        # Signal the consumer to stop
        if self.sqs_consumer:
            await self.sqs_consumer.stop()

        # Wait for worker task to complete with timeout
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                # Force cancel if it doesn't stop gracefully
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

        self._worker_task = None
        self.sqs_consumer = None

    async def wait_for_processing(
        self,
        expected_count: int = 1,
        timeout: float = 10.0,
        check_interval: float = 0.1,
    ) -> list[dict[str, Any]]:
        """
        Wait for the worker to process a specific number of messages.

        This is useful for synchronizing tests with async message processing.

        Args:
            expected_count: Number of messages to wait for
            timeout: Maximum time to wait (seconds)
            check_interval: How often to check progress (seconds)

        Returns:
            list: List of processed message data

        Raises:
            TimeoutError: If expected_count not reached within timeout
        """
        elapsed = 0.0

        while elapsed < timeout:
            if len(self._processed_messages) >= expected_count:
                return self._processed_messages[:expected_count]

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        raise TimeoutError(
            f"Worker did not process {expected_count} messages within {timeout}s "
            f"(processed: {len(self._processed_messages)})"
        )

    async def wait_for_idle(self, idle_time: float = 2.0) -> None:
        """
        Wait for the worker to become idle (no processing for idle_time seconds).

        Useful for ensuring all messages have been processed before verification.

        Args:
            idle_time: How long to wait with no new messages (seconds)
        """
        previous_count = len(self._processed_messages)
        await asyncio.sleep(idle_time)

        if len(self._processed_messages) != previous_count:
            # Still processing, wait again
            await self.wait_for_idle(idle_time)

    def get_processed_messages(self) -> list[dict[str, Any]]:
        """Get list of all messages processed by this worker."""
        return self._processed_messages.copy()

    def get_processing_errors(self) -> list[Exception]:
        """Get list of all processing errors encountered."""
        return self._processing_errors.copy()

    def clear_history(self) -> None:
        """Clear processed messages and error history."""
        self._processed_messages.clear()
        self._processing_errors.clear()

    async def simulate_crash(self) -> None:
        """
        Simulate a worker crash by immediately canceling the worker task.

        This does NOT call stop() - it forcibly kills the worker mid-processing.
        Useful for testing crash recovery and lock expiration scenarios.
        """
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self.running = False
        self._worker_task = None


@pytest_asyncio.fixture
async def worker_instance(test_sqs_queue, sqs_client, mock_payment_token_client):
    """
    Create a single worker instance for testing.

    This fixture:
    1. Creates a WorkerTestInstance
    2. Yields it to the test
    3. Ensures it's stopped after the test completes

    Usage:
        async def test_something(worker_instance):
            await worker_instance.start()
            # ... do testing ...
            # Worker will be automatically stopped after test

    Returns:
        WorkerTestInstance: Managed worker instance
    """
    worker = WorkerTestInstance(
        queue_url=test_sqs_queue,
        sqs_client=sqs_client,
        payment_token_client=mock_payment_token_client,
    )

    yield worker

    # Cleanup: ensure worker is stopped
    if worker.running:
        await worker.stop()


@pytest_asyncio.fixture
async def multiple_workers(test_sqs_queue, sqs_client, mock_payment_token_client):
    """
    Factory fixture for creating multiple worker instances.

    Useful for testing concurrency, lock contention, and race conditions.

    Usage:
        async def test_concurrency(multiple_workers):
            workers = await multiple_workers(count=3)
            # Start all workers
            for worker in workers:
                await worker.start()
            # ... test concurrent processing ...

    Returns:
        Callable: Async function that returns list of worker instances
    """
    created_workers: list[WorkerTestInstance] = []

    async def _create_workers(count: int) -> list[WorkerTestInstance]:
        """
        Create multiple worker instances.

        Args:
            count: Number of workers to create

        Returns:
            list: List of WorkerTestInstance objects
        """
        workers = []
        for i in range(count):
            worker = WorkerTestInstance(
                queue_url=test_sqs_queue,
                worker_id=f"test-worker-{i}",
                sqs_client=sqs_client,
                payment_token_client=mock_payment_token_client,
            )
            workers.append(worker)
            created_workers.append(worker)

        return workers

    yield _create_workers

    # Cleanup: stop all created workers
    for worker in created_workers:
        if worker.running:
            await worker.stop()


@pytest_asyncio.fixture
async def start_worker(worker_instance):
    """
    Helper fixture that automatically starts a worker and ensures cleanup.

    This is a convenience fixture for tests that just need a running worker
    without manual start/stop management.

    Usage:
        async def test_something(start_worker):
            # Worker is already started and will auto-stop after test
            # Just publish messages and verify results
            ...

    Returns:
        WorkerTestInstance: Running worker instance
    """
    await worker_instance.start()

    yield worker_instance

    # Cleanup happens in worker_instance fixture
