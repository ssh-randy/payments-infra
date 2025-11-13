"""Debug script to test payment token creation and capture detailed errors."""
import asyncio
import os
import sys
import uuid

# Add paths for imports
sys.path.insert(0, '.')
sys.path.insert(0, '../shared/python')

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import httpx
from payments_proto.payments.v1 import payment_token_pb2

TEST_BDK = b"0" * 32
TEST_API_KEY = "test-api-key-12345"


def derive_device_key(bdk: bytes, device_token: str) -> bytes:
    """Derive device-specific encryption key from BDK."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"payment-token-v1:" + device_token.encode('utf-8'),
        backend=default_backend()
    ).derive(bdk)


def encrypt_card_data(
    card_number: str,
    exp_month: int,
    exp_year: int,
    cvv: str,
    device_token: str,
) -> bytes:
    """Encrypt card data as device would."""
    # Derive device key
    device_key = derive_device_key(TEST_BDK, device_token)

    # Create PaymentData protobuf message
    pb_payment_data = payment_token_pb2.PaymentData(
        card_number=card_number,
        exp_month=str(exp_month),
        exp_year=str(exp_year),
        cvv=cvv,
        cardholder_name="Test Cardholder",
    )

    print(f"\n[DEBUG] PaymentData protobuf:")
    print(f"  card_number: {pb_payment_data.card_number}")
    print(f"  exp_month: {pb_payment_data.exp_month}")
    print(f"  exp_year: {pb_payment_data.exp_year}")
    print(f"  cvv: {pb_payment_data.cvv}")
    print(f"  cardholder_name: {pb_payment_data.cardholder_name}")

    # Serialize to bytes
    plaintext = pb_payment_data.SerializeToString()
    print(f"\n[DEBUG] Serialized plaintext length: {len(plaintext)} bytes")

    # Encrypt with AES-GCM
    aesgcm = AESGCM(device_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    print(f"[DEBUG] Nonce length: {len(nonce)} bytes")
    print(f"[DEBUG] Ciphertext length: {len(ciphertext)} bytes")

    # Return nonce + ciphertext
    encrypted = nonce + ciphertext
    print(f"[DEBUG] Total encrypted data length: {len(encrypted)} bytes")

    return encrypted


async def test_token_creation():
    """Test token creation with detailed error reporting."""
    print("=" * 80)
    print("DEBUG: Testing Payment Token Creation")
    print("=" * 80)

    # Generate test data
    device_token = f"device_{uuid.uuid4().hex[:16]}"
    restaurant_id = str(uuid.uuid4())
    idempotency_key = str(uuid.uuid4())

    print(f"\n[TEST DATA]")
    print(f"  device_token: {device_token}")
    print(f"  restaurant_id: {restaurant_id}")
    print(f"  idempotency_key: {idempotency_key}")

    # Encrypt card data
    print(f"\n[ENCRYPTION]")
    encrypted_payment_data = encrypt_card_data(
        card_number="4532015112830366",
        exp_month=12,
        exp_year=2025,
        cvv="123",
        device_token=device_token,
    )

    # Create protobuf request
    print(f"\n[PROTOBUF REQUEST]")
    pb_request = payment_token_pb2.CreatePaymentTokenRequest(
        restaurant_id=restaurant_id,
        encrypted_payment_data=encrypted_payment_data,
        device_token=device_token,
        idempotency_key=idempotency_key,
    )

    print(f"  restaurant_id: {pb_request.restaurant_id}")
    print(f"  device_token: {pb_request.device_token}")
    print(f"  encrypted_payment_data length: {len(pb_request.encrypted_payment_data)} bytes")
    print(f"  idempotency_key: {pb_request.idempotency_key}")

    serialized_request = pb_request.SerializeToString()
    print(f"  Serialized request length: {len(serialized_request)} bytes")

    # Make HTTP request
    print(f"\n[HTTP REQUEST]")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "http://localhost:8001/v1/payment-tokens",
                content=serialized_request,
                headers={
                    "Content-Type": "application/x-protobuf",
                    "X-Idempotency-Key": idempotency_key,
                    "Authorization": f"Bearer {TEST_API_KEY}",
                },
            )

            print(f"  Status Code: {response.status_code}")
            print(f"  Response Headers: {dict(response.headers)}")

            if response.status_code in (200, 201):
                print(f"\n[SUCCESS] Token created!")
                pb_response = payment_token_pb2.CreatePaymentTokenResponse()
                pb_response.ParseFromString(response.content)
                print(f"  payment_token: {pb_response.payment_token}")
                print(f"  restaurant_id: {pb_response.restaurant_id}")
                print(f"  expires_at: {pb_response.expires_at}")
            else:
                print(f"\n[ERROR] Request failed!")
                print(f"  Status: {response.status_code}")
                print(f"  Response body (text): {response.text}")
                print(f"  Response body (bytes): {response.content}")

        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            raise


if __name__ == "__main__":
    asyncio.run(test_token_creation())
