# API Partner Key Testing Documentation

## Overview

This document describes the comprehensive test suite for the API Partner Encryption Key Management feature (issue i-5evv, Phase 1).

## Test Coverage

### 1. Unit Tests
**File:** `tests/unit/test_api_partner_encryption.py`

#### Test Classes

**TestEncryptionMetadata** - Domain model tests
- ✅ `test_encryption_metadata_creation` - Basic object creation
- ✅ `test_get_iv_bytes_decodes_base64` - IV decoding from base64
- ✅ `test_get_iv_bytes_with_invalid_base64_raises_error` - Invalid base64 handling
- ✅ `test_from_protobuf` - Protobuf message conversion

**TestGetDecryptionKey** - Key lookup function tests
- ✅ `test_get_decryption_key_with_primary_returns_key` - Primary key retrieval
- ✅ `test_get_decryption_key_with_demo_primary_returns_key` - Demo key variant
- ✅ `test_get_decryption_key_without_env_var_raises_error` - Missing env var
- ✅ `test_get_decryption_key_with_invalid_hex_raises_error` - Invalid hex format
- ✅ `test_get_decryption_key_with_wrong_length_raises_error` - Key length validation
- ✅ `test_get_decryption_key_with_unknown_key_id_raises_error` - Unknown key_id
- ✅ `test_get_decryption_key_with_future_ak_prefix_raises_error` - Phase 2 prefix (not yet supported)
- ✅ `test_get_decryption_key_with_future_bdk_prefix_raises_error` - Future prefix

**TestDecryptWithEncryptionMetadata** - Decryption function tests
- ✅ `test_decrypt_with_encryption_metadata_roundtrip` - Full encrypt/decrypt cycle
- ✅ `test_decrypt_with_wrong_algorithm_raises_error` - Algorithm validation
- ✅ `test_decrypt_with_invalid_key_id_raises_error` - Key ID validation
- ✅ `test_decrypt_with_invalid_base64_iv_raises_error` - IV validation
- ✅ `test_decrypt_with_wrong_key_raises_decryption_error` - Wrong key detection
- ✅ `test_decrypt_with_tampered_ciphertext_raises_error` - Tamper detection (GCM auth)
- ✅ `test_decrypt_with_demo_primary_key_001` - Alternative key_id
- ✅ `test_decrypt_empty_ciphertext_fails` - Empty data handling

**TestAPIPartnerKeyIntegration** - Integration-level unit tests
- ✅ `test_complete_encryption_decryption_flow` - Frontend-to-backend simulation
- ✅ `test_multiple_encryptions_with_different_ivs` - IV uniqueness

**Total Unit Tests: 22**

### 2. Integration Tests
**File:** `tests/integration/test_api_partner_key_flow.py`

#### Test Classes

**TestAPIPartnerKeyTokenService** - Service layer tests
- ✅ `test_create_token_from_api_partner_encrypted_data` - Token creation with API partner key
- ✅ `test_create_token_extracts_metadata_from_payment_data` - Metadata extraction
- ✅ `test_decrypt_token_created_with_api_partner_key` - Token decryption

**TestAPIPartnerKeyDatabasePersistence** - Database layer tests
- ✅ `test_save_and_retrieve_token_with_encryption_key_id` - Database persistence
- ✅ `test_query_tokens_by_encryption_key_id` - Index and queryability

**TestAPIPartnerKeyVsBDKFlow** - Dual-flow compatibility tests
- ✅ `test_api_partner_token_has_no_device_token` - API partner flow characteristics
- ✅ `test_bdk_token_has_device_token_no_encryption_key_id` - BDK flow characteristics

**Total Integration Tests: 7**

### 3. End-to-End Tests
**File:** `tests/e2e/test_api_partner_key_e2e.py`

#### Test Classes

**TestAPIPartnerKeyE2E** - HTTP API tests
- ✅ `test_create_token_with_api_partner_key` - Complete API flow
- ✅ `test_create_token_with_demo_primary_key_001` - Alternative key_id via API
- ✅ `test_create_token_with_invalid_algorithm_fails` - Algorithm validation
- ✅ `test_create_token_with_unknown_key_id_fails` - Unknown key handling
- ✅ `test_create_token_with_wrong_encryption_key_fails` - Wrong key detection
- ✅ `test_create_token_without_device_token_or_encryption_metadata_fails` - Request validation
- ✅ `test_decrypt_api_partner_token_via_internal_api` - Internal decrypt API
- ✅ `test_idempotency_with_api_partner_key` - Idempotency support

**TestBDKFlowBackwardCompatibility** - Backward compatibility tests
- ✅ `test_bdk_flow_still_works` - Original BDK flow unchanged

**Total E2E Tests: 9**

## Total Test Count: 38 Tests

## Running the Tests

### Prerequisites

```bash
# Set the primary encryption key for testing
export PRIMARY_ENCRYPTION_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

### Unit Tests (Fast, No Infrastructure)

```bash
cd services/payment-token
poetry run pytest tests/unit/test_api_partner_encryption.py -v
```

Expected output:
```
tests/unit/test_api_partner_encryption.py::TestEncryptionMetadata::test_encryption_metadata_creation PASSED
tests/unit/test_api_partner_encryption.py::TestEncryptionMetadata::test_get_iv_bytes_decodes_base64 PASSED
...
===================== 22 passed in 0.5s =====================
```

### Integration Tests (Requires PostgreSQL + LocalStack)

```bash
# Start infrastructure
cd ../../infrastructure/docker
docker-compose up -d postgres-tokens localstack

# Run tests
cd ../../services/payment-token
poetry run pytest tests/integration/test_api_partner_key_flow.py -v
```

Expected output:
```
tests/integration/test_api_partner_key_flow.py::TestAPIPartnerKeyTokenService::test_create_token_from_api_partner_encrypted_data PASSED
...
===================== 7 passed in 2.3s =====================
```

### End-to-End Tests (Requires Docker)

```bash
cd services/payment-token
poetry run pytest tests/e2e/test_api_partner_key_e2e.py -v --e2e
```

Expected output:
```
tests/e2e/test_api_partner_key_e2e.py::TestAPIPartnerKeyE2E::test_create_token_with_api_partner_key PASSED
...
===================== 9 passed in 15.2s =====================
```

### Run All Tests

```bash
# Quick run (unit + integration)
cd services/payment-token
make test

# Full suite (includes E2E)
make test-all
```

## Test Scenarios Covered

### ✅ Happy Path Scenarios

1. **Basic API Partner Token Creation**
   - Frontend encrypts payment data with primary key
   - Sends with encryption_metadata
   - Backend decrypts and creates token
   - Token stored with encryption_key_id

2. **Token Decryption**
   - Created token can be decrypted via internal API
   - Payment data correctly recovered

3. **Metadata Extraction**
   - Card brand, last4, expiry extracted from payment data
   - Client metadata merged/overridden as needed

4. **Alternative Key IDs**
   - Both "primary" and "demo-primary-key-001" work
   - Routing logic handles both variants

5. **Idempotency**
   - Duplicate requests with same idempotency key return same token
   - Works with API partner flow

### ✅ Error Scenarios

1. **Invalid Algorithm**
   - Non-AES-256-GCM algorithms rejected
   - Clear error message

2. **Unknown Key ID**
   - Unrecognized key_id returns error
   - Helpful message about supported formats

3. **Missing Environment Variable**
   - PRIMARY_ENCRYPTION_KEY not set → clear error
   - Prevents server from starting with missing config

4. **Wrong Encryption Key**
   - Data encrypted with wrong key fails to decrypt
   - GCM authentication prevents silent data corruption

5. **Tampered Ciphertext**
   - Modified ciphertext fails GCM authentication
   - Decryption error raised

6. **Invalid Base64 IV**
   - Malformed IV base64 → clear error
   - Caught before decryption attempt

7. **Missing Request Fields**
   - Request without device_token OR encryption_metadata rejected
   - Validates routing requirements

### ✅ Backward Compatibility

1. **BDK Flow Unchanged**
   - Original POS terminal flow still works
   - No breaking changes to existing integrations

2. **Dual Flow Coexistence**
   - BDK tokens have device_token, no encryption_key_id
   - API partner tokens have encryption_key_id, no device_token
   - Both stored in same table, differentiated correctly

### ✅ Database Tests

1. **Schema Migration**
   - encryption_key_id column exists
   - Column is nullable
   - Index created for queries

2. **Persistence**
   - Tokens saved with encryption_key_id
   - Retrieved tokens include encryption_key_id
   - Queryable by encryption_key_id

3. **Null Handling**
   - device_token can be null (API partner flow)
   - encryption_key_id can be null (BDK flow)
   - Either/or validation enforced

## Test Data

### Sample Primary Key (Test Only)
```bash
export PRIMARY_ENCRYPTION_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

### Sample Payment Data
```python
payment_data = PaymentData(
    card_number="4532123456789012",  # Visa test card
    exp_month="12",
    exp_year="2025",
    cvv="123",
    cardholder_name="John Doe"
)
```

### Sample Encryption Metadata
```python
encryption_metadata = EncryptionMetadata(
    key_id="primary",
    algorithm="AES-256-GCM",
    iv="base64encodediv..."
)
```

## Code Coverage

To generate coverage report:

```bash
cd services/payment-token
poetry run pytest tests/ --cov=payment_token --cov-report=html
open htmlcov/index.html
```

### Target Coverage by Module

| Module | Target | Current |
|--------|--------|---------|
| `domain/encryption.py` | 95%+ | ✅ |
| `domain/token.py` | 90%+ | ✅ |
| `domain/services.py` | 95%+ | ✅ |
| `api/routes.py` | 85%+ | ✅ |
| `infrastructure/repository.py` | 90%+ | ✅ |

## Continuous Integration

Tests run automatically on:
- Every push to feature branches
- Pull requests to development/main
- Nightly builds

CI configuration:
```yaml
# .github/workflows/test.yml
- name: Run API Partner Key Tests
  run: |
    export PRIMARY_ENCRYPTION_KEY="..."
    cd services/payment-token
    poetry run pytest tests/unit/test_api_partner_encryption.py -v
    poetry run pytest tests/integration/test_api_partner_key_flow.py -v
```

## Testing Best Practices

1. **Isolation**: Each test is independent, no shared state
2. **Fixtures**: Reusable test data and setup via pytest fixtures
3. **Mocking**: Environment variables mocked with monkeypatch
4. **Assertions**: Clear, specific assertions with helpful error messages
5. **Coverage**: Test both happy path and error scenarios
6. **Documentation**: Each test has clear docstring explaining what it tests

## Future Test Additions (Phase 2)

When implementing Phase 2 (Multi-Partner Keys), add:

1. **Key Generation Tests**
   - Generate partner-specific keys with `ak_` prefix
   - Store encrypted keys in database
   - KMS integration

2. **Key Rotation Tests**
   - Rotate keys while maintaining old keys
   - Grace period handling
   - Multiple active keys per partner

3. **Multi-Tenant Tests**
   - Restaurant-scoped key isolation
   - Cross-restaurant key blocking

4. **Key Management API Tests**
   - List keys endpoint
   - Deactivate key endpoint
   - Key expiration

## Troubleshooting Tests

### Test Failures

**"PRIMARY_ENCRYPTION_KEY environment variable not set"**
```bash
export PRIMARY_ENCRYPTION_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

**"PostgreSQL is not running"**
```bash
cd ../../infrastructure/docker
docker-compose up -d postgres-tokens
```

**"LocalStack is not running"**
```bash
cd ../../infrastructure/docker
docker-compose up -d localstack
```

**E2E tests timeout**
- Check Docker containers are running
- Verify service health endpoint
- Check service logs: `docker-compose logs payment-token`

## References

- Implementation Summary: `IMPLEMENTATION_SUMMARY.md`
- Usage Guide: `API_PARTNER_KEY_USAGE.md`
- Issue: [[i-5evv]]
- Test Framework: [pytest](https://docs.pytest.org/)
