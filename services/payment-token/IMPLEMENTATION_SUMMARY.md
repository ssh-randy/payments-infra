# Implementation Summary: API Partner Encryption Key Management (Phase 1)

## Issue: i-5evv

**Status:** ✅ COMPLETE

**Phase:** Phase 1 - Primary Key Demo Support

## What Was Implemented

### 1. Protobuf Schema Updates ✅
**File:** `shared/protos/payments/v1/payment_token.proto`

- Added `EncryptionMetadata` message with fields:
  - `key_id`: Key identifier (e.g., "primary", "ak_{uuid}")
  - `algorithm`: Encryption algorithm ("AES-256-GCM")
  - `iv`: Base64-encoded initialization vector

- Updated `CreatePaymentTokenRequest`:
  - Made `device_token` optional (BDK flow only)
  - Added `encryption_metadata` field (API partner flow only)
  - Both flows supported through single endpoint

### 2. Database Migration ✅
**File:** `services/payment-token/alembic/versions/25d03b185558_add_encryption_key_id_to_payment_tokens_.py`

Changes to `payment_tokens` table:
- ✅ Added `encryption_key_id VARCHAR(255)` column
- ✅ Added index `idx_payment_tokens_key_id` for key rotation queries
- ✅ Made `device_token` nullable (not used in API partner flow)

**To apply:** Run `poetry run alembic upgrade head`

### 3. Domain Model Updates ✅

#### EncryptionMetadata Class
**File:** `src/payment_token/domain/encryption.py:39-83`

```python
class EncryptionMetadata(NamedTuple):
    key_id: str
    algorithm: str
    iv: str  # Base64-encoded

    @classmethod
    def from_protobuf(cls, pb_metadata) -> "EncryptionMetadata":
        # Converts protobuf to domain model

    def get_iv_bytes(self) -> bytes:
        # Decodes base64 IV to bytes
```

#### PaymentToken Updates
**File:** `src/payment_token/domain/token.py:235-283`

- ✅ Added `encryption_key_id: Optional[str]` field
- ✅ Made `device_token: Optional[str]` (was required)
- ✅ Added validation: Either `device_token` OR `encryption_key_id` must be present
- ✅ Updated `create()` factory method to accept both parameters

### 4. Encryption Functions ✅

#### get_decryption_key()
**File:** `src/payment_token/domain/encryption.py:311-377`

```python
def get_decryption_key(key_id: str) -> bytes:
    """Look up decryption key by key_id.

    Routing:
    - "primary" or "demo-primary-key-001" → Primary demo key (Phase 1)
    - "ak_{uuid}" → API partner keys (Phase 2 - future)
    - "bdk_{id}" → BDK-based keys (future)
    """
    if key_id in ("demo-primary-key-001", "primary"):
        # Get from PRIMARY_ENCRYPTION_KEY environment variable
        return bytes.fromhex(os.environ["PRIMARY_ENCRYPTION_KEY"])

    # Future: API partner keys from database
    # Future: BDK-based key derivation

    raise ValueError(f"Unknown key_id: {key_id}")
```

**Security:**
- Phase 1: Environment variable (suitable for demo)
- Phase 2: Will use KMS-encrypted keys from database

#### decrypt_with_encryption_metadata()
**File:** `src/payment_token/domain/encryption.py:380-438`

```python
def decrypt_with_encryption_metadata(
    encrypted_data: bytes,
    encryption_metadata: EncryptionMetadata
) -> bytes:
    """Decrypt using API partner key flow."""
    # 1. Validate algorithm is AES-256-GCM
    # 2. Look up decryption key by key_id
    # 3. Decode IV from base64
    # 4. Decrypt with AES-GCM
    # 5. Return plaintext
```

### 5. TokenService Updates ✅

#### New Method: create_token_from_api_partner_encrypted_data()
**File:** `src/payment_token/domain/services.py:157-268`

```python
def create_token_from_api_partner_encrypted_data(
    self,
    restaurant_id: str,
    encrypted_payment_data: bytes,
    encryption_metadata: EncryptionMetadata,
    service_encryption_key: bytes,
    service_key_version: str,
    metadata_dict: Optional[dict] = None,
    expiration_hours: int = 24,
) -> PaymentToken:
    """API Partner Key Flow implementation."""
    # 1. Decrypt with encryption_metadata
    # 2. Parse payment data
    # 3. Extract metadata
    # 4. Re-encrypt with service key
    # 5. Create PaymentToken with encryption_key_id
```

### 6. API Endpoint Updates ✅
**File:** `src/payment_token/api/routes.py:create_payment_token`

**Lines 120-268:** Complete dual-flow routing implementation

```python
# Determine flow based on presence of encryption_metadata
has_encryption_metadata = pb_request.HasField("encryption_metadata")
has_device_token = pb_request.HasField("device_token")

if has_encryption_metadata:
    # API Partner Key Flow
    encryption_metadata = EncryptionMetadata.from_protobuf(...)
    token = token_service.create_token_from_api_partner_encrypted_data(...)
else:
    # BDK Flow (original implementation)
    bdk = kms_client.get_bdk(...)
    token = token_service.create_token_from_device_encrypted_data(...)
```

**Features:**
- ✅ Single endpoint supports both flows
- ✅ Automatic routing based on request fields
- ✅ Backward compatible with existing BDK flow
- ✅ Proper error handling for both flows

### 7. Repository Updates ✅
**File:** `src/payment_token/infrastructure/repository.py`

- ✅ Updated `save_token()` to include `encryption_key_id`
- ✅ Updated `_to_domain_entity()` to include `encryption_key_id`
- ✅ ORM model handles nullable `device_token` and `encryption_key_id`

### 8. Infrastructure Model Updates ✅
**File:** `src/payment_token/infrastructure/models.py`

```python
class PaymentToken(Base):
    # Existing fields...
    encryption_key_id: Mapped[str | None] = mapped_column(...)
    device_token: Mapped[str | None] = mapped_column(...)  # Now nullable
```

## Success Criteria (Phase 1)

- ✅ Payment token creation accepts `encryption_metadata`
- ✅ Decryption uses `key_id` to look up correct key
- ✅ Primary key works for demo (from environment variable)
- ✅ `encryption_key_id` stored with payment token
- ✅ Code structured to support multiple key types (ak_, bdk_, primary)
- ✅ BDK flow remains functional (backward compatible)
- ✅ Frontend can use new API partner key flow

## Files Modified

1. `shared/protos/payments/v1/payment_token.proto` - Protocol buffers definition
2. `services/payment-token/alembic/versions/25d03b185558_*.py` - Database migration
3. `services/payment-token/src/payment_token/domain/encryption.py` - Encryption logic
4. `services/payment-token/src/payment_token/domain/token.py` - Domain models
5. `services/payment-token/src/payment_token/domain/services.py` - Business logic
6. `services/payment-token/src/payment_token/api/routes.py` - API endpoints
7. `services/payment-token/src/payment_token/infrastructure/models.py` - ORM models
8. `services/payment-token/src/payment_token/infrastructure/repository.py` - Data access

## New Files Created

1. `services/payment-token/API_PARTNER_KEY_USAGE.md` - Usage documentation
2. `services/payment-token/IMPLEMENTATION_SUMMARY.md` - This file

## Testing

### Setup for Testing

```bash
# 1. Set primary encryption key (32 bytes / 64 hex chars)
export PRIMARY_ENCRYPTION_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

# 2. Run database migration
cd services/payment-token
poetry run alembic upgrade head

# 3. Generate protobuf code
bash ../../scripts/generate_protos.sh

# 4. Run tests
poetry run pytest tests/
```

### Integration Test Example

See `API_PARTNER_KEY_USAGE.md` for complete examples.

```python
# Create payment token with API partner key
request = CreatePaymentTokenRequest(
    restaurant_id="550e8400-e29b-41d4-a716-446655440000",
    encrypted_payment_data=encrypted_data,  # AES-256-GCM encrypted
    encryption_metadata=EncryptionMetadata(
        key_id="primary",
        algorithm="AES-256-GCM",
        iv=base64_iv
    )
)

response = send_request(request)
assert response.payment_token.startswith("pt_")
```

## Architecture Benefits

### Single Endpoint, Multiple Flows

**Endpoint:** `POST /v1/payment-tokens`

**Automatically routes to:**
1. **API Partner Flow** if `encryption_metadata` provided
2. **BDK Flow** if `device_token` provided (no encryption_metadata)

**Benefits:**
- ✅ No API versioning needed
- ✅ No breaking changes to existing integrations
- ✅ Easy to add more flows in future (Phase 2, Phase 3)
- ✅ Self-documenting via key_id prefixes (primary, ak_, bdk_)

### Key ID Routing

Current implementation supports future expansion:

| Flow | Key ID Prefix | Status |
|------|---------------|--------|
| Online Demo | `primary`, `demo-primary-key-001` | ✅ Phase 1 |
| Online Production | `ak_{uuid}` | 🔄 Phase 2 |
| POS Terminals | `bdk_{id}` | 🔄 Future |

The routing logic is already in place - just needs implementation for future phases.

## Next Steps (Phase 2)

Not implemented yet, but architected for:

1. **API Partner Keys Table**
   ```sql
   CREATE TABLE api_partner_keys (
       key_id VARCHAR(255) PRIMARY KEY,  -- ak_{uuid}
       restaurant_id UUID,
       encrypted_decryption_key TEXT,    -- KMS-encrypted
       is_active BOOLEAN,
       ...
   );
   ```

2. **Key Generation API**
   - `POST /v1/api-keys/generate` - Generate partner keys
   - `GET /v1/api-keys` - List keys
   - `POST /v1/api-keys/{key_id}/rotate` - Key rotation

3. **Enhanced get_decryption_key()**
   - Database lookup for `ak_{uuid}` keys
   - KMS decryption
   - Restaurant-scoped key isolation

## Security Audit

### Phase 1 Security Posture

✅ **Good for Demo:**
- Encryption in transit (TLS)
- Strong encryption at rest (AES-256-GCM)
- Key stored in environment (acceptable for demo)
- All payment data re-encrypted with service key
- Audit trail via `encryption_key_id`

⚠️ **Production Requirements (Phase 2):**
- Move keys to KMS-encrypted storage
- Implement key rotation
- Add per-partner key isolation
- Enhanced audit logging

## Known Limitations

1. **Single Primary Key:** All API partners share same demo key in Phase 1
2. **Environment Variable Storage:** Not suitable for production
3. **No Key Rotation:** Phase 1 doesn't support rotating the primary key
4. **No Key Expiration:** Keys don't expire automatically

These are intentional trade-offs for Phase 1 demo. All will be addressed in Phase 2.

## Deployment Checklist

Before deploying to any environment:

- [ ] Set `PRIMARY_ENCRYPTION_KEY` environment variable
- [ ] Run database migration (`alembic upgrade head`)
- [ ] Generate protobuf code (`generate_protos.sh`)
- [ ] Restart payment-token service
- [ ] Verify BDK flow still works (backward compatibility test)
- [ ] Test API partner flow with demo key
- [ ] Check logs for any errors

## Support & Troubleshooting

### Common Issues

**Error: "PRIMARY_ENCRYPTION_KEY environment variable not set"**
- Solution: Set the environment variable with a 64-character hex string

**Error: "Invalid base64 IV"**
- Solution: Ensure IV is base64-encoded in the request

**Error: "Either device_token or encryption_key_id must be provided"**
- Solution: Check that exactly one of these is provided in the request

**Error: "Unknown key_id"**
- Solution: For Phase 1, use "primary" or "demo-primary-key-001"

### Debug Logging

```python
import logging
logging.getLogger('payment_token.domain.encryption').setLevel(logging.DEBUG)
```

## References

- Issue: [[i-5evv]]
- Frontend Spec: [[s-63fi]]
- Payment Token Service Spec: [[s-7ujm]]
- Usage Guide: `API_PARTNER_KEY_USAGE.md`
