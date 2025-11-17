"""SQS FIFO consumer for auth request processing."""

import asyncio
import base64
import json
from typing import Any, Awaitable, Callable

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from payments_proto.payments.v1.events_pb2 import AuthRequestQueuedMessage
from auth_processor_worker.logging_config import get_logger

logger = get_logger(__name__)


class SQSConsumer:
    """
    SQS FIFO consumer that dequeues auth requests from the queue.

    Implements:
    - Long polling with 20-second wait time
    - Batch size: 1 (for simplicity)
    - Visibility timeout: 30 seconds
    - Message deletion after successful processing
    - Graceful shutdown
    - Error handling and retry logic based on ApproximateReceiveCount
    """

    def __init__(
        self,
        queue_url: str,
        batch_size: int = 1,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 30,
        aws_region: str = "us-east-1",
        aws_endpoint_url: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        sqs_client: Any = None,
    ) -> None:
        """
        Initialize the SQS consumer.

        Args:
            queue_url: SQS queue URL
            batch_size: Number of messages to fetch per batch (default: 1)
            wait_time_seconds: Long polling wait time (default: 20)
            visibility_timeout: Message visibility timeout in seconds (default: 30)
            aws_region: AWS region (default: us-east-1)
            aws_endpoint_url: AWS endpoint URL (for LocalStack)
            message_handler: Async callback to process messages
            sqs_client: Pre-configured SQS client (for testing). If provided, the consumer
                        will use this client instead of creating its own session.
        """
        self.queue_url = queue_url
        self.batch_size = batch_size
        self.wait_time_seconds = wait_time_seconds
        self.visibility_timeout = visibility_timeout
        self.aws_region = aws_region
        self.aws_endpoint_url = aws_endpoint_url
        self.message_handler = message_handler
        self.running = False
        self._session: aioboto3.Session | None = None
        self._sqs_client: Any = None
        self._injected_client: Any = sqs_client  # Store injected client for tests
        self.logger = get_logger(self.__class__.__name__)

    async def start(self) -> None:
        """
        Start the consumer and begin polling for messages.

        This method:
        1. Initializes the SQS client (or uses injected one for tests)
        2. Enters a long-polling loop
        3. Processes messages via the message handler
        4. Continues until stop() is called
        """
        self.running = True
        self.logger.info(
            "sqs_consumer_starting",
            queue_url=self.queue_url,
            batch_size=self.batch_size,
            wait_time_seconds=self.wait_time_seconds,
            visibility_timeout=self.visibility_timeout,
        )

        # Use injected client if provided (for tests), otherwise create our own
        if self._injected_client:
            # Test mode: use provided client
            self._sqs_client = self._injected_client
            try:
                await self._polling_loop()
            except Exception as e:
                self.logger.error("sqs_consumer_error", error=str(e), exc_info=True)
                raise
            finally:
                self.logger.info("sqs_consumer_stopped")
        else:
            # Production mode: create and manage our own session
            self._session = aioboto3.Session()
            async with self._session.client(
                "sqs",
                region_name=self.aws_region,
                endpoint_url=self.aws_endpoint_url,
            ) as sqs_client:
                self._sqs_client = sqs_client

                try:
                    await self._polling_loop()
                except Exception as e:
                    self.logger.error("sqs_consumer_error", error=str(e), exc_info=True)
                    raise
                finally:
                    self.logger.info("sqs_consumer_stopped")

    async def stop(self) -> None:
        """
        Gracefully stop the consumer.

        Sets running flag to False, which will cause the polling loop to exit
        after the current iteration completes.
        """
        self.logger.info("sqs_consumer_stopping")
        self.running = False

    async def _polling_loop(self) -> None:
        """
        Main polling loop that fetches and processes messages.

        Uses long polling to reduce empty receives and API calls.
        Continues until stop() is called.
        """
        while self.running:
            try:
                await self.process_messages()
            except Exception as e:
                self.logger.error("polling_loop_error", error=str(e), exc_info=True)
                # Brief backoff before retrying to avoid tight error loop
                await asyncio.sleep(1)

    async def process_messages(self) -> None:
        """
        Fetch and process a batch of messages from SQS.

        Steps:
        1. Receive messages (long polling)
        2. For each message:
           a. Parse message body
           b. Extract auth_request_id
           c. Call message handler
           d. Delete message if processing succeeds
        3. Handle errors and retry logic based on ApproximateReceiveCount
        """
        if not self._sqs_client:
            raise RuntimeError("SQS client not initialized. Call start() first.")

        try:
            # Receive messages with long polling
            response = await self._sqs_client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=self.batch_size,
                WaitTimeSeconds=self.wait_time_seconds,
                VisibilityTimeout=self.visibility_timeout,
                AttributeNames=["ApproximateReceiveCount", "MessageGroupId"],
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            if not messages:
                # No messages available (normal for long polling)
                self.logger.debug("no_messages_received")
                return

            self.logger.info("messages_received", count=len(messages))

            # Process each message
            for message in messages:
                await self._process_single_message(message)

        except (BotoCoreError, ClientError) as e:
            self.logger.error("sqs_receive_error", error=str(e), exc_info=True)
            # Don't raise - let the polling loop continue
        except Exception as e:
            self.logger.error("unexpected_process_error", error=str(e), exc_info=True)
            # Don't raise - let the polling loop continue

    async def _process_single_message(self, message: dict[str, Any]) -> None:
        """
        Process a single SQS message.

        Args:
            message: SQS message dict containing Body, ReceiptHandle, Attributes, etc.
        """
        receipt_handle = message.get("ReceiptHandle")
        message_id = message.get("MessageId")
        attributes = message.get("Attributes", {})
        receive_count = int(attributes.get("ApproximateReceiveCount", 0))

        self.logger.info(
            "processing_message",
            message_id=message_id,
            receive_count=receive_count,
        )

        try:
            # Parse message body - it's a base64-encoded protobuf message
            body_str = message["Body"]

            # Decode base64
            try:
                body_bytes = base64.b64decode(body_str)
            except Exception as e:
                self.logger.error(
                    "base64_decode_error",
                    message_id=message_id,
                    error=str(e),
                )
                # Delete malformed message
                await self._delete_message(receipt_handle, message_id)
                return

            # Parse protobuf
            try:
                queued_msg = AuthRequestQueuedMessage()
                queued_msg.ParseFromString(body_bytes)
                auth_request_id = queued_msg.auth_request_id
            except Exception as e:
                self.logger.error(
                    "protobuf_parse_error",
                    message_id=message_id,
                    error=str(e),
                )
                # Delete malformed message
                await self._delete_message(receipt_handle, message_id)
                return

            if not auth_request_id:
                self.logger.error(
                    "missing_auth_request_id",
                    message_id=message_id,
                )
                # Delete malformed message to avoid reprocessing
                await self._delete_message(receipt_handle, message_id)
                return

            # Prepare message data for handler
            message_data = {
                "auth_request_id": auth_request_id,
                "message_id": message_id,
                "receipt_handle": receipt_handle,
                "receive_count": receive_count,
                "body": {
                    "auth_request_id": auth_request_id,
                    "restaurant_id": queued_msg.restaurant_id,
                    "created_at": queued_msg.created_at,
                },
                "attributes": attributes,
            }

            # Call the message handler
            if self.message_handler:
                await self.message_handler(message_data)
            else:
                self.logger.warning(
                    "no_message_handler",
                    message_id=message_id,
                    auth_request_id=auth_request_id,
                )

            # Delete message after successful processing
            await self._delete_message(receipt_handle, message_id)

        except Exception as e:
            self.logger.error(
                "message_processing_error",
                message_id=message_id,
                error=str(e),
                receive_count=receive_count,
                exc_info=True,
            )
            # Don't delete - let visibility timeout expire for retry
            # The message will be reprocessed based on the queue's redrive policy

    async def _delete_message(self, receipt_handle: str | None, message_id: str) -> None:
        """
        Delete a message from SQS after successful processing.

        Args:
            receipt_handle: SQS receipt handle for the message
            message_id: Message ID for logging
        """
        if not receipt_handle:
            self.logger.error("missing_receipt_handle", message_id=message_id)
            return

        if not self._sqs_client:
            raise RuntimeError("SQS client not initialized")

        try:
            await self._sqs_client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )
            self.logger.info("message_deleted", message_id=message_id)

        except (BotoCoreError, ClientError) as e:
            self.logger.error(
                "message_delete_error",
                message_id=message_id,
                error=str(e),
                exc_info=True,
            )
            # Don't raise - message will become visible again after timeout
