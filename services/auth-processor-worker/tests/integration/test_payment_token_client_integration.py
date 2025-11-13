"""Integration tests for Payment Token Service client.

These tests verify the client works end-to-end with a mock HTTP server
that simulates the Payment Token Service API.
"""

import sys
from pathlib import Path

import pytest
from aiohttp import web

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


class MockPaymentTokenService:
    """Mock Payment Token Service HTTP server for integration testing."""

    def __init__(self):
        self.app = web.Application()
        self.app.router.add_post("/internal/v1/decrypt", self.handle_decrypt)
        self.runner = None
        self.site = None
        self.port = None

        # Configure mock responses
        self.mock_responses = {}

    def configure_response(self, payment_token: str, response_type: str, **kwargs):
        """
        Configure mock response for a specific payment token.

        Args:
            payment_token: Token to configure response for
            response_type: One of "success", "not_found", "expired", "forbidden", "error"
            **kwargs: Additional arguments for the response (e.g., payment_data for success)
        """
        self.mock_responses[payment_token] = {"type": response_type, **kwargs}

    async def handle_decrypt(self, request: web.Request) -> web.Response:
        """Handle /internal/v1/decrypt endpoint."""
        # Verify headers
        assert request.headers.get("Content-Type") == "application/x-protobuf"
        assert request.headers.get("X-Service-Auth") is not None
        assert request.headers.get("X-Request-ID") is not None

        # Parse request
        body = await request.read()
        req_proto = payment_token_pb2.DecryptPaymentTokenRequest()
        req_proto.ParseFromString(body)

        # Get configured response for this token
        mock_config = self.mock_responses.get(req_proto.payment_token)

        if not mock_config:
            # Default: token not found
            return web.Response(status=404)

        response_type = mock_config["type"]

        if response_type == "success":
            # Return successful decryption
            payment_data = mock_config.get("payment_data")
            metadata = mock_config.get("metadata", {})

            response_proto = payment_token_pb2.DecryptPaymentTokenResponse(
                payment_data=payment_data, metadata=metadata
            )

            return web.Response(
                body=response_proto.SerializeToString(),
                status=200,
                headers={"Content-Type": "application/x-protobuf"},
            )

        elif response_type == "not_found":
            return web.Response(status=404)

        elif response_type == "expired":
            return web.Response(status=410)

        elif response_type == "forbidden":
            return web.Response(status=403)

        elif response_type == "error":
            status_code = mock_config.get("status_code", 500)
            return web.Response(status=status_code)

        else:
            return web.Response(status=500)

    async def start(self):
        """Start the mock HTTP server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        # Use port 0 to get a random available port
        self.site = web.TCPSite(self.runner, "localhost", 0)
        await self.site.start()

        # Get the actual port assigned
        self.port = self.site._server.sockets[0].getsockname()[1]

    async def stop(self):
        """Stop the mock HTTP server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    @property
    def base_url(self) -> str:
        """Get the base URL of the mock server."""
        return f"http://localhost:{self.port}"


@pytest.fixture
async def mock_service():
    """Create and start a mock Payment Token Service."""
    service = MockPaymentTokenService()
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
def mock_payment_data():
    """Create mock payment data."""
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


@pytest.mark.integration
class TestPaymentTokenServiceClientIntegration:
    """Integration test suite for Payment Token Service client."""

    @pytest.mark.asyncio
    async def test_decrypt_success_end_to_end(self, mock_service, mock_payment_data):
        """Test successful decryption end-to-end with mock server."""
        # Configure mock service to return success
        mock_service.configure_response(
            payment_token="pt_test123",
            response_type="success",
            payment_data=mock_payment_data,
            metadata={"card_brand": "visa", "last4": "1111"},
        )

        # Create client pointing to mock service
        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            # Decrypt token
            result = await client.decrypt(
                payment_token="pt_test123",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )

            # Verify decrypted data
            assert result.card_number == "4111111111111111"
            assert result.exp_month == "12"
            assert result.exp_year == "2025"
            assert result.cvv == "123"
            assert result.cardholder_name == "John Doe"
            assert result.billing_address.line1 == "123 Main St"
            assert result.billing_address.city == "New York"

    @pytest.mark.asyncio
    async def test_decrypt_token_not_found_end_to_end(self, mock_service):
        """Test 404 TokenNotFound error end-to-end."""
        # Configure mock service to return 404
        mock_service.configure_response(
            payment_token="pt_notfound", response_type="not_found"
        )

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            with pytest.raises(TokenNotFound):
                await client.decrypt(
                    payment_token="pt_notfound",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_token_expired_end_to_end(self, mock_service):
        """Test 410 TokenExpired error end-to-end."""
        # Configure mock service to return 410
        mock_service.configure_response(payment_token="pt_expired", response_type="expired")

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            with pytest.raises(TokenExpired):
                await client.decrypt(
                    payment_token="pt_expired",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_forbidden_end_to_end(self, mock_service):
        """Test 403 Forbidden error end-to-end."""
        # Configure mock service to return 403
        mock_service.configure_response(payment_token="pt_forbidden", response_type="forbidden")

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            with pytest.raises(Forbidden):
                await client.decrypt(
                    payment_token="pt_forbidden",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_service_error_end_to_end(self, mock_service):
        """Test 500 server error end-to-end."""
        # Configure mock service to return 500
        mock_service.configure_response(
            payment_token="pt_error", response_type="error", status_code=500
        )

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            with pytest.raises(ProcessorTimeout):
                await client.decrypt(
                    payment_token="pt_error",
                    restaurant_id="rest_abc",
                    requesting_service="auth-processor-worker",
                )

    @pytest.mark.asyncio
    async def test_decrypt_multiple_tokens(self, mock_service, mock_payment_data):
        """Test decrypting multiple different tokens."""
        # Configure multiple tokens
        mock_service.configure_response(
            payment_token="pt_token1",
            response_type="success",
            payment_data=mock_payment_data,
            metadata={"card_brand": "visa"},
        )

        # Create a different payment data for token2
        payment_data2 = payment_token_pb2.PaymentData(
            card_number="5555555555554444",
            exp_month="06",
            exp_year="2026",
            cvv="456",
            cardholder_name="Jane Smith",
        )

        mock_service.configure_response(
            payment_token="pt_token2",
            response_type="success",
            payment_data=payment_data2,
            metadata={"card_brand": "mastercard"},
        )

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="test-auth-token",
            timeout_seconds=5.0,
        ) as client:
            # Decrypt first token
            result1 = await client.decrypt(
                payment_token="pt_token1",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )
            assert result1.card_number == "4111111111111111"
            assert result1.cardholder_name == "John Doe"

            # Decrypt second token
            result2 = await client.decrypt(
                payment_token="pt_token2",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )
            assert result2.card_number == "5555555555554444"
            assert result2.cardholder_name == "Jane Smith"

    @pytest.mark.asyncio
    async def test_request_headers_verification(self, mock_service, mock_payment_data):
        """
        Test that the client sends correct headers.

        This test relies on the mock service's handle_decrypt method
        which asserts the presence of required headers.
        """
        mock_service.configure_response(
            payment_token="pt_test",
            response_type="success",
            payment_data=mock_payment_data,
            metadata={},
        )

        async with PaymentTokenServiceClient(
            base_url=mock_service.base_url,
            service_auth_token="my-secret-token",
            timeout_seconds=5.0,
        ) as client:
            # This will succeed only if headers are correct
            # (the mock service asserts header presence)
            await client.decrypt(
                payment_token="pt_test",
                restaurant_id="rest_abc",
                requesting_service="auth-processor-worker",
            )
