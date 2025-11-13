"""Main entry point for Auth Processor Worker Service."""

import asyncio
import signal
import sys
import uuid
from typing import Any

from auth_processor_worker.config import settings
from auth_processor_worker.handlers.processor import ProcessingResult, process_auth_request
from auth_processor_worker.infrastructure.sqs_consumer import SQSConsumer
from auth_processor_worker.logging_config import configure_logging, get_logger

# Configure logging
configure_logging(
    log_level="DEBUG" if settings.debug else "INFO",
    format_as_json=settings.environment != "development",
    include_correlation_id=True,
)

logger = get_logger(__name__)


class Worker:
    """Main worker class that orchestrates auth request processing."""

    def __init__(self) -> None:
        self.running = False
        self.logger = get_logger(self.__class__.__name__)
        self.sqs_consumer: SQSConsumer | None = None

    async def _handle_message(self, message_data: dict[str, Any]) -> None:
        """
        Handle a message from SQS.

        This is the callback that processes each auth request message.
        It orchestrates the complete auth request workflow:
        1. Acquire distributed lock
        2. Check for void events
        3. Fetch auth request details
        4. Call payment token service
        5. Call payment processor
        6. Record events and update read model atomically
        7. Release lock

        Args:
            message_data: Parsed message data including auth_request_id, receipt_handle, etc.
        """
        auth_request_id_str = message_data["auth_request_id"]
        receive_count = message_data["receive_count"]

        self.logger.info(
            "handling_auth_request",
            auth_request_id=auth_request_id_str,
            receive_count=receive_count,
        )

        try:
            # Convert auth_request_id string to UUID
            auth_request_id = uuid.UUID(auth_request_id_str)

            # Process the auth request
            result = await process_auth_request(
                auth_request_id=auth_request_id,
                worker_id=settings.worker.worker_id,
                receive_count=receive_count,
            )

            self.logger.info(
                "auth_request_processed",
                auth_request_id=auth_request_id_str,
                result=result,
                receive_count=receive_count,
            )

            # Note: SQS message deletion happens in the SQS consumer
            # after this handler completes successfully. If we raise an
            # exception, the message will not be deleted and will be retried.
            #
            # For RETRYABLE_FAILURE, we want the message to be retried,
            # so we raise an exception to prevent deletion.
            if result == ProcessingResult.RETRYABLE_FAILURE:
                raise Exception("Retryable failure - message will be retried")

        except Exception as e:
            self.logger.error(
                "message_handling_error",
                auth_request_id=auth_request_id_str,
                error=str(e),
                exc_info=True,
            )
            # Re-raise to prevent SQS message deletion
            raise

    async def start(self) -> None:
        """Start the worker and begin processing messages."""
        self.running = True
        self.logger.info(
            "worker_starting",
            worker_id=settings.worker.worker_id,
            environment=settings.environment,
            sqs_queue_url=settings.worker.sqs_queue_url,
        )

        # Initialize SQS consumer
        self.sqs_consumer = SQSConsumer(
            queue_url=settings.worker.sqs_queue_url,
            batch_size=settings.worker.batch_size,
            wait_time_seconds=settings.worker.wait_time_seconds,
            visibility_timeout=settings.worker.visibility_timeout,
            aws_region=settings.aws_region,
            aws_endpoint_url=settings.aws_endpoint_url,
            message_handler=self._handle_message,
        )

        try:
            # Start the SQS consumer (this will block until stop() is called)
            await self.sqs_consumer.start()
        except Exception as e:
            self.logger.error("worker_error", error=str(e), exc_info=True)
            raise

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self.logger.info("worker_stopping")
        self.running = False

        # Stop the SQS consumer
        if self.sqs_consumer:
            await self.sqs_consumer.stop()

        # TODO: Clean up database connections, release locks, etc.


async def main() -> None:
    """Main application entry point."""
    worker = Worker()

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig: Any) -> None:
        logger.info("received_signal", signal=signal.Signals(sig).name)
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.error("fatal_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        await worker.stop()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
