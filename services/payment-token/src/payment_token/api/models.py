"""Pydantic models for JSON API requests/responses.

This module provides JSON schema models that mirror the protobuf definitions,
enabling the API to accept both JSON and protobuf formats.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EncryptionMetadataModel(BaseModel):
    """Encryption metadata for API partner key flow (JSON format)."""

    key_id: str = Field(..., description="Encryption key identifier")
    algorithm: str = Field(..., description="Encryption algorithm (e.g., AES-256-GCM)")
    iv: str = Field(..., description="Initialization vector (base64 encoded)")


class CreatePaymentTokenRequestJSON(BaseModel):
    """JSON request model for creating a payment token.

    Supports two encryption flows:
    1. API Partner Key Flow (online ordering): Use encryption_metadata
    2. BDK Flow (POS terminals): Use device_token
    """

    restaurant_id: str = Field(..., description="Restaurant/merchant UUID")
    encrypted_payment_data: str = Field(
        ..., description="Encrypted payment data (base64 encoded)"
    )
    encryption_metadata: Optional[EncryptionMetadataModel] = Field(
        None, description="Encryption metadata for API partner key flow"
    )
    device_token: Optional[str] = Field(
        None, description="Device token for BDK-based encryption flow"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "restaurant_id": "12345678-1234-5678-1234-567812345678",
                "encrypted_payment_data": "SGVsbG8gV29ybGQh...==",
                "encryption_metadata": {
                    "key_id": "demo-primary-key-001",
                    "algorithm": "AES-256-GCM",
                    "iv": "cmFuZG9taXY="
                },
                "metadata": {
                    "card_brand": "visa",
                    "last4": "4242"
                }
            }
        }


class CreatePaymentTokenResponseJSON(BaseModel):
    """JSON response model for payment token creation."""

    payment_token: str = Field(..., description="Generated payment token")
    restaurant_id: str = Field(..., description="Restaurant/merchant UUID")
    expires_at: int = Field(..., description="Expiration timestamp (Unix epoch)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Token metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "payment_token": "pt_1234567890abcdef",
                "restaurant_id": "12345678-1234-5678-1234-567812345678",
                "expires_at": 1699999999,
                "metadata": {
                    "card_brand": "visa",
                    "last4": "4242"
                }
            }
        }


class GetPaymentTokenResponseJSON(BaseModel):
    """JSON response model for retrieving payment token metadata."""

    payment_token: str = Field(..., description="Payment token")
    restaurant_id: str = Field(..., description="Restaurant/merchant UUID")
    created_at: int = Field(..., description="Creation timestamp (Unix epoch)")
    expires_at: int = Field(..., description="Expiration timestamp (Unix epoch)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Token metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "payment_token": "pt_1234567890abcdef",
                "restaurant_id": "12345678-1234-5678-1234-567812345678",
                "created_at": 1699990000,
                "expires_at": 1699999999,
                "metadata": {
                    "card_brand": "visa",
                    "last4": "4242"
                }
            }
        }
