"""Pydantic models for JSON API requests/responses.

This module provides JSON schema models for authorization API endpoints,
replacing protobuf for this external-facing API.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuthorizeRequestJSON(BaseModel):
    """JSON request model for creating an authorization request."""

    restaurant_id: str = Field(..., description="Restaurant/merchant UUID")
    payment_token: str = Field(..., description="Payment token from tokenization")
    amount_cents: int = Field(..., description="Amount in cents", gt=0)
    currency: str = Field(..., description="Currency code (e.g., USD)")
    idempotency_key: str = Field(..., description="Client idempotency key")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "restaurant_id": "12345678-1234-5678-1234-567812345678",
                "payment_token": "pt_1234567890abcdef",
                "amount_cents": 1299,
                "currency": "USD",
                "idempotency_key": "order-12345-payment-1",
                "metadata": {
                    "order_id": "order-12345",
                    "cart_items": [
                        {
                            "name": "Burger",
                            "quantity": 1,
                            "unit_price_cents": 899
                        },
                        {
                            "name": "Fries",
                            "quantity": 1,
                            "unit_price_cents": 400
                        }
                    ]
                }
            }
        }


class AuthorizationResultJSON(BaseModel):
    """JSON model for authorization result details."""

    processor_name: Optional[str] = Field(None, description="Payment processor name")
    processor_auth_id: Optional[str] = Field(None, description="Processor authorization ID")
    processor_auth_code: Optional[str] = Field(None, description="Processor auth code")
    processor_decline_code: Optional[str] = Field(None, description="Processor decline code")
    decline_reason: Optional[str] = Field(None, description="Human-readable decline reason")
    network_status: Optional[str] = Field(None, description="Card network status")
    risk_score: Optional[int] = Field(None, description="Risk assessment score")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class AuthorizeResponseJSON(BaseModel):
    """JSON response model for authorization request."""

    auth_request_id: str = Field(..., description="Authorization request ID")
    status: str = Field(
        ...,
        description="Authorization status (PENDING, PROCESSING, AUTHORIZED, DENIED, FAILED)"
    )
    status_url: Optional[str] = Field(None, description="URL to poll for status updates")
    result: Optional[AuthorizationResultJSON] = Field(None, description="Authorization result (if completed)")

    class Config:
        json_schema_extra = {
            "example": {
                "auth_request_id": "87654321-4321-8765-4321-876543218765",
                "status": "AUTHORIZED",
                "result": {
                    "processor_name": "stripe",
                    "processor_auth_id": "ch_1234567890",
                    "processor_auth_code": "123456",
                    "network_status": "approved_by_network"
                }
            }
        }


class GetAuthStatusResponseJSON(BaseModel):
    """JSON response model for getting authorization status."""

    auth_request_id: str = Field(..., description="Authorization request ID")
    status: str = Field(
        ...,
        description="Authorization status (PENDING, PROCESSING, AUTHORIZED, DENIED, FAILED)"
    )
    created_at: int = Field(..., description="Creation timestamp (Unix epoch)")
    updated_at: int = Field(..., description="Last update timestamp (Unix epoch)")
    result: Optional[AuthorizationResultJSON] = Field(None, description="Authorization result (if completed)")

    class Config:
        json_schema_extra = {
            "example": {
                "auth_request_id": "87654321-4321-8765-4321-876543218765",
                "status": "AUTHORIZED",
                "created_at": 1699990000,
                "updated_at": 1699990005,
                "result": {
                    "processor_name": "stripe",
                    "processor_auth_id": "ch_1234567890",
                    "processor_auth_code": "123456",
                    "network_status": "approved_by_network",
                    "risk_score": 15
                }
            }
        }
