# API Partner Encryption Key Usage Guide

## Overview

The Payment Token Service now supports **two encryption flows** through a single API endpoint:

1. **BDK Flow** (POS Terminals) - Original implementation using device-based encryption
2. **API Partner Key Flow** (Online Ordering) - NEW: Uses pre-shared encryption keys for web/mobile apps

This document covers the new **API Partner Key Flow** for Phase 1 (demo implementation).

## Architecture

### Single Endpoint, Dual Flow

**Endpoint:** `POST /v1/payment-tokens`

**Routing Logic:**
- If `encryption_metadata` is provided → API Partner Key Flow
- If `device_token` is provided (and no encryption_metadata) → BDK Flow
- The backend automatically routes to the correct decryption method

### Key ID Formats

| Flow | Key ID Format | Example | Phase |
|------|---------------|---------|-------|
| Online (Demo) | `primary` or `demo-primary-key-001` | `primary` | Phase 1 ✅ |
| Online (Production) | `ak_{uuid}` | `ak_550e8400-e29b-41d4-a716-446655440000` | Phase 2 (Future) |
| POS Terminals | `bdk_{identifier}` | `bdk_terminal_001` | Future |

## Phase 1: Primary Key Demo

### Setup

1. **Set Environment Variable:**
   ```bash
   # Generate a 32-byte (256-bit) key in hex format
   export PRIMARY_ENCRYPTION_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
   ```

2. **Run Database Migration:**
   ```bash
   cd services/payment-token
   poetry run alembic upgrade head
   ```

3. **Verify Protobuf Generation:**
   ```bash
   bash ../../scripts/generate_protos.sh
   ```

### API Usage

#### Request Format (Protobuf)

```protobuf
message CreatePaymentTokenRequest {
  string restaurant_id = 1;
  bytes encrypted_payment_data = 2;

  // NEW: Encryption metadata for API partner key flow
  EncryptionMetadata encryption_metadata = 6;

  // Optional
  string idempotency_key = 4;
  map<string, string> metadata = 5;
}

message EncryptionMetadata {
  string key_id = 1;      // "primary" or "demo-primary-key-001"
  string algorithm = 2;   // "AES-256-GCM"
  string iv = 3;          // Base64-encoded IV/nonce
}
```

#### Frontend Encryption Example (JavaScript/TypeScript)

```typescript
import crypto from 'crypto';

// Your pre-shared encryption key (32 bytes)
const encryptionKey = Buffer.from('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef', 'hex');

// Payment data to encrypt
const paymentData = {
  card_number: "4532123456789012",
  exp_month: "12",
  exp_year: "2025",
  cvv: "123",
  cardholder_name: "John Doe"
};

// Serialize to protobuf bytes
const paymentDataBytes = serializePaymentData(paymentData);

// Encrypt with AES-256-GCM
const iv = crypto.randomBytes(12); // 96-bit nonce
const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey, iv);
const encryptedData = Buffer.concat([
  cipher.update(paymentDataBytes),
  cipher.final(),
  cipher.getAuthTag() // GCM auth tag appended
]);

// Create payment token request
const request = {
  restaurant_id: "550e8400-e29b-41d4-a716-446655440000",
  encrypted_payment_data: encryptedData,
  encryption_metadata: {
    key_id: "primary",              // Use demo primary key
    algorithm: "AES-256-GCM",
    iv: iv.toString('base64')       // Base64-encoded IV
  },
  idempotency_key: "unique-request-id",
  metadata: {
    card_brand: "visa",
    last4: "9012"
  }
};

// Send protobuf-encoded request
const response = await sendProtobufRequest('/v1/payment-tokens', request);
```

#### Python Example

```python
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from payments_proto.payments.v1 import payment_token_pb2

# Get primary encryption key from environment
encryption_key = bytes.fromhex(os.environ['PRIMARY_ENCRYPTION_KEY'])

# Payment data
payment_data = payment_token_pb2.PaymentData(
    card_number="4532123456789012",
    exp_month="12",
    exp_year="2025",
    cvv="123",
    cardholder_name="John Doe"
)

# Serialize to bytes
payment_data_bytes = payment_data.SerializeToString()

# Encrypt with AES-256-GCM
aesgcm = AESGCM(encryption_key)
iv = os.urandom(12)  # 96-bit nonce
encrypted_data = aesgcm.encrypt(iv, payment_data_bytes, None)

# Create request
request = payment_token_pb2.CreatePaymentTokenRequest(
    restaurant_id="550e8400-e29b-41d4-a716-446655440000",
    encrypted_payment_data=encrypted_data,
    encryption_metadata=payment_token_pb2.EncryptionMetadata(
        key_id="primary",
        algorithm="AES-256-GCM",
        iv=base64.b64encode(iv).decode('utf-8')
    ),
    idempotency_key="unique-request-id",
    metadata={"card_brand": "visa", "last4": "9012"}
)

# Send request (protobuf-encoded)
response_bytes = send_request(request.SerializeToString())
response = payment_token_pb2.CreatePaymentTokenResponse()
response.ParseFromString(response_bytes)
print(f"Token created: {response.payment_token}")
```

### Backend Flow

1. **Request Validation:**
   - Checks that either `encryption_metadata` OR `device_token` is provided
   - Routes to API Partner Key flow if `encryption_metadata` is present

2. **Decryption:**
   ```python
   # payment_token/domain/encryption.py

   # Look up decryption key by key_id
   decryption_key = get_decryption_key("primary")
   # Returns PRIMARY_ENCRYPTION_KEY from environment

   # Decrypt with AES-256-GCM
   decrypt_with_encryption_metadata(encrypted_data, encryption_metadata)
   ```

3. **Token Storage:**
   - Token is re-encrypted with service rotating key
   - `encryption_key_id` is stored for audit trail
   - `device_token` is NULL for API partner flow

4. **Response:**
   ```protobuf
   message CreatePaymentTokenResponse {
     string payment_token = 1;        // "pt_550e8400-..."
     string restaurant_id = 2;
     int64 expires_at = 3;
     map<string, string> metadata = 4;
   }
   ```

## Database Schema

### Updated payment_tokens Table

```sql
CREATE TABLE payment_tokens (
    payment_token VARCHAR(64) PRIMARY KEY,
    restaurant_id UUID NOT NULL,
    encrypted_payment_data BYTEA NOT NULL,
    encryption_key_version VARCHAR(50) NOT NULL,

    -- NEW: Key ID for API partner flow (NULL for BDK flow)
    encryption_key_id VARCHAR(255),

    -- NOW NULLABLE: Only used in BDK flow
    device_token VARCHAR(255),

    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    metadata JSONB
);

CREATE INDEX idx_payment_tokens_key_id ON payment_tokens(encryption_key_id);
```

## Security Considerations

### Phase 1 (Current)
- ✅ Primary key stored in environment variable (secure for demo)
- ✅ All payment data re-encrypted with service rotating key
- ✅ `encryption_key_id` stored for audit trail
- ✅ AES-256-GCM provides authenticated encryption

### Phase 2 (Future Production)
- 🔄 Decryption keys encrypted with AWS KMS
- 🔄 Per-partner encryption keys with `ak_{uuid}` prefix
- 🔄 Key rotation support
- 🔄 Database-backed key management

## Testing

### Unit Tests

```python
def test_get_decryption_key_primary():
    os.environ['PRIMARY_ENCRYPTION_KEY'] = '00112233' * 8
    key = get_decryption_key('primary')
    assert len(key) == 32

def test_decrypt_with_encryption_metadata():
    metadata = EncryptionMetadata(
        key_id='primary',
        algorithm='AES-256-GCM',
        iv='base64encodediv'
    )
    decrypted = decrypt_with_encryption_metadata(encrypted_data, metadata)
    assert decrypted == expected_plaintext
```

### Integration Test

```python
def test_create_token_with_api_partner_key():
    # Encrypt payment data
    encrypted_data = encrypt_payment_data(payment_data, primary_key)

    # Create request
    request = CreatePaymentTokenRequest(
        restaurant_id=test_restaurant_id,
        encrypted_payment_data=encrypted_data,
        encryption_metadata=EncryptionMetadata(
            key_id='primary',
            algorithm='AES-256-GCM',
            iv=base64_iv
        )
    )

    # Send request
    response = client.post('/v1/payment-tokens', request.SerializeToString())

    # Verify
    assert response.status_code == 201
    token = parse_response(response.content)
    assert token.payment_token.startswith('pt_')

    # Verify token stored with encryption_key_id
    db_token = get_token_from_db(token.payment_token)
    assert db_token.encryption_key_id == 'primary'
    assert db_token.device_token is None
```

## Migration from BDK Flow

The API Partner Key flow **coexists** with the existing BDK flow:

- **BDK Requests** (POS terminals): Continue to work unchanged
  - Provide `device_token`
  - Do NOT provide `encryption_metadata`

- **API Partner Requests** (Online ordering): Use new flow
  - Provide `encryption_metadata`
  - Do NOT provide `device_token`

No breaking changes to existing integrations!

## Next Steps (Phase 2)

Future enhancements for production readiness:

1. **Multi-Partner Key Management**
   - API to generate partner-specific keys with `ak_{uuid}` prefix
   - Store encrypted keys in `api_partner_keys` table
   - KMS-backed key encryption

2. **Key Rotation**
   - Automatic 90-day rotation
   - Grace period for old keys
   - Partner notification system

3. **Advanced Features**
   - Key expiration
   - Per-restaurant key scoping
   - Audit logging dashboard

## Support

For questions or issues:
- Check logs: `services/payment-token/logs/`
- Run tests: `make test` in payment-token directory
- Review spec: [[s-63fi]] for frontend encryption details
