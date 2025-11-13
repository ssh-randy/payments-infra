"""SQS client for sending messages to queues."""

import base64
import boto3
import structlog
from botocore.config import Config

from authorization_api.config import settings

logger = structlog.get_logger()

# Global SQS client
_sqs_client = None


def get_sqs_client():
    """Get or create SQS client.

    Returns:
        boto3 SQS client
    """
    global _sqs_client
    if _sqs_client is None:
        # Configure boto3
        config = Config(
            region_name=settings.aws_region,
            retries={
                "max_attempts": 3,
                "mode": "adaptive",
            },
        )

        # Create client
        client_kwargs = {"config": config}

        if settings.aws_endpoint_url:
            client_kwargs["endpoint_url"] = settings.aws_endpoint_url

        if settings.aws_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id

        if settings.aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

        _sqs_client = boto3.client("sqs", **client_kwargs)

        logger.info(
            "sqs_client_created",
            region=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
        )

    return _sqs_client


async def send_to_auth_requests_queue(
    message_body: bytes,
    message_deduplication_id: str,
    message_group_id: str,
) -> None:
    """Send message to auth requests FIFO queue.

    Args:
        message_body: Serialized protobuf message
        message_deduplication_id: Deduplication ID (auth_request_id)
        message_group_id: Message group ID (restaurant_id for ordering)
    """
    client = get_sqs_client()

    try:
        # Encode binary protobuf as base64 for SQS
        message_str = base64.b64encode(message_body).decode("ascii")

        response = client.send_message(
            QueueUrl=settings.auth_requests_queue_url,
            MessageBody=message_str,
            MessageDeduplicationId=message_deduplication_id,
            MessageGroupId=message_group_id,
        )

        logger.info(
            "message_sent_to_auth_requests_queue",
            message_id=response["MessageId"],
            deduplication_id=message_deduplication_id,
            group_id=message_group_id,
        )

    except Exception as e:
        logger.error(
            "failed_to_send_to_auth_requests_queue",
            error=str(e),
            deduplication_id=message_deduplication_id,
        )
        raise


async def send_to_void_requests_queue(
    message_body: bytes,
) -> None:
    """Send message to void requests queue (standard queue).

    Args:
        message_body: Serialized protobuf message
    """
    client = get_sqs_client()

    try:
        # Encode binary protobuf as base64 for SQS
        message_str = base64.b64encode(message_body).decode("ascii")

        response = client.send_message(
            QueueUrl=settings.void_requests_queue_url,
            MessageBody=message_str,
        )

        logger.info(
            "message_sent_to_void_requests_queue",
            message_id=response["MessageId"],
        )

    except Exception as e:
        logger.error(
            "failed_to_send_to_void_requests_queue",
            error=str(e),
        )
        raise
