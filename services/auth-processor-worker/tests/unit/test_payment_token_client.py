"""Unit tests for Payment Token Service client."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# Add shared proto directory to Python path
_shared_proto_path = (
    Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "python"
)
if str(_shared_proto_path) not in sys.path:
    sys.path.insert(0, str(_shared_proto_path))

from payments_proto.payments.v1 import common_pb2, payment_token_pb2

from auth_processor_worker.clients.payment_token_client import PaymentTokenServiceClient
from auth_processor_worker.models.exceptions import (
    Forbidden,
    ProcessorTimeout,
    TokenExpired,
    TokenNotFound,
)


@pytest.fixture
def client():
    """Create a Payment Token Service client for testing."""
    return PaymentTokenServiceClient(
        base_url="http://localhost:8000",
        service_auth_token="test-auth-token",
        timeout_seconds=5.0,
    )


@pytest.fixture
def mock_payment_data():
    """Create mock payment data protobuf."""
    address = common_pb2.Address(
        line1="123 Main St",
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
    )

    return payment_token_pb2.PaymentData(
        card_number="4111111111111111",
        exp_month="12",
        exp_year="2025",
        cvv="123",
        cardholder_name="John Doe",
        billing_address=address,
    )


class TestPaymentTokenServiceClient:
    """Test suite for Payment Token Service client."""

    @pytest.mark.asyncio
    async def test_decrypt_success(self, client, mock_payment_data):
        """Test successful token decryption."""
        # Build expected response
        response_proto = payment_token_pb2.DecryptPaymentTokenResponse(
            payment_data=mock_payment_data,
            metadata={"card_brand": "visa", "last4": "1111"},
        )

        # Mock HTTP response
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = response_proto.SerializeToString()
        mock_response.raise_for_status = AsyncMock()

        with patch.object(client.http_client, "post", return_value=mock_response):
            result = await client.decrypt(
                payment_token="pt_test123",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )

            # Verify result
            assert result.card_number == "4111111111111111"
            assert result.exp_month == "12"
            assert result.exp_year == "2025"
            assert result.cvv == "123"
            assert result.cardholder_name == "John Doe"
            assert result.billing_address.city == "New York"

            # Verify request was made correctly
            client.http_client.post.assert_called_once()
            call_args = client.http_client.post.call_args

            assert call_args[0][0] == "http://localhost:8000/internal/v1/decrypt"
            assert call_args[1]["headers"]["Content-Type"] == "application/x-protobuf"
            assert call_args[1]["headers"]["X-Service-Auth"] == "test-auth-token"
            assert "X-Request-ID" in call_args[1]["headers"]

            # Verify request body is valid protobuf
            request_proto = payment_token_pb2.DecryptPaymentTokenRequest()
            request_proto.ParseFromString(call_args[1]["content"])
            assert request_proto.payment_token == "pt_test123"
            assert request_proto.restaurant_id == "rest_abc"
            assert request_proto.requesting_service == "auth-processor-worker"

    @pytest.mark.asyncio
    async def test_decrypt_token_not_found(self, client):
        """Test 404 TokenNotFound error."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 404

        with patch.object(client.http_client, "post", return_value=mock_response):
            with pytest.raises(TokenNotFound, match="Token pt_test123 not found"):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_token_expired(self, client):
        """Test 410 TokenExpired error."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 410

        with patch.object(client.http_client, "post", return_value=mock_response):
            with pytest.raises(TokenExpired, match="Token pt_test123 expired"):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_forbidden(self, client):
        """Test 403 Forbidden error."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 403

        with patch.object(client.http_client, "post", return_value=mock_response):
            with pytest.raises(Forbidden, match="Unauthorized access to token pt_test123"):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_service_error_500(self, client):
        """Test 500 server error."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500

        with patch.object(client.http_client, "post", return_value=mock_response):
            with pytest.raises(
                ProcessorTimeout, match="Payment Token Service unavailable.*500"
            ):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_service_error_503(self, client):
        """Test 503 service unavailable error."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 503

        with patch.object(client.http_client, "post", return_value=mock_response):
            with pytest.raises(
                ProcessorTimeout, match="Payment Token Service unavailable.*503"
            ):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_timeout(self, client):
        """Test request timeout."""
        with patch.object(
            client.http_client, "post", side_effect=httpx.TimeoutException("Timeout")
        ):
            with pytest.raises(ProcessorTimeout, match="Payment Token Service timeout"):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_connection_error(self, client):
        """Test network/connection error."""
        with patch.object(
            client.http_client,
            "post",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(
                ProcessorTimeout, match="Payment Token Service request error"
            ):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_base_url_trailing_slash_handling(self):
        """Test that trailing slash in base_url is handled correctly."""
        client = PaymentTokenServiceClient(
            base_url="http://localhost:8000/",  # Note trailing slash
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = payment_token_pb2.DecryptPaymentTokenResponse(
            payment_data=payment_token_pb2.PaymentData(
                card_number="4111111111111111",
                exp_month="12",
                exp_year="2025",
                cvv="123",
                cardholder_name="Test",
            )
        ).SerializeToString()
        mock_response.raise_for_status = AsyncMock()

        with patch.object(client.http_client, "post", return_value=mock_response):
            await client.decrypt(
                payment_token="pt_test123",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )

            # Verify URL is correctly formed (no double slash)
            call_args = client.http_client.post.call_args
            assert call_args[0][0] == "http://localhost:8000/internal/v1/decrypt"

        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_payment_data):
        """Test client can be used as async context manager."""
        response_proto = payment_token_pb2.DecryptPaymentTokenResponse(
            payment_data=mock_payment_data,
            metadata={},
        )

        async with PaymentTokenServiceClient(
            base_url="http://localhost:8000",
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            mock_response = AsyncMock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.content = response_proto.SerializeToString()
            mock_response.raise_for_status = AsyncMock()

            with patch.object(client.http_client, "post", return_value=mock_response):
                result = await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

                assert result.card_number == "4111111111111111"

    @pytest.mark.asyncio
    async def test_correlation_id_uniqueness(self, client, mock_payment_data):
        """Test that each request gets a unique correlation ID."""
        response_proto = payment_token_pb2.DecryptPaymentTokenResponse(
            payment_data=mock_payment_data,
            metadata={},
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = response_proto.SerializeToString()
        mock_response.raise_for_status = AsyncMock()

        correlation_ids = []

        with patch.object(client.http_client, "post", return_value=mock_response):
            # Make multiple requests
            for _ in range(3):
                await client.decrypt(
                    payment_token="pt_test123",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

                # Extract correlation ID from last call
                call_args = client.http_client.post.call_args
                correlation_id = call_args[1]["headers"]["X-Request-ID"]
                correlation_ids.append(correlation_id)

        # All correlation IDs should be unique
        assert len(correlation_ids) == 3
        assert len(set(correlation_ids)) == 3

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test client close method."""
        with patch.object(client.http_client, "aclose", new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()
