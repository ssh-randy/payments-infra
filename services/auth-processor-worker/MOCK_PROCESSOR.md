# Mock Processor Documentation

## Overview

The `MockProcessor` is a testing implementation of the `PaymentProcessor` interface that simulates payment authorization without making real API calls. It's designed to mirror the behavior of production processors (especially Stripe) for comprehensive end-to-end testing.

## Purpose

- ✅ Enable fast, deterministic testing without external API dependencies
- ✅ Test complete authorization workflows including success, decline, and error scenarios
- ✅ No API credentials or network connectivity required
- ✅ CI/CD friendly - no secrets needed
- ✅ Complements real processor integration tests

## Key Features

### 1. Stripe Test Card Compatibility

The mock processor uses the same test card numbers as Stripe's official test cards, making it easy to switch between mock and real Stripe testing:

| Card Number | Behavior | Description |
|------------|----------|-------------|
| `4242424242424242` | ✅ Success | Generic Visa success |
| `5555555555554444` | ✅ Success | Mastercard success |
| `378282246310005` | ✅ Success | American Express success |
| `4000000000000002` | ❌ Decline | Generic decline |
| `4000000000009995` | ❌ Decline | Insufficient funds |
| `4000000000000069` | ❌ Decline | Expired card |
| `4000000000000127` | ❌ Decline | Incorrect CVC |
| `4000000000000341` | ❌ Decline | Lost card |
| `4000000000000226` | ❌ Decline | Fraudulent card |
| `4000002500003155` | ⚠️ Requires Action | 3D Secure required |
| `4000000000000119` | ⏱️ Timeout | Retryable error |
| `4000000000009987` | ⏱️ Rate Limit | Retryable error |

**Reference:** https://docs.stripe.com/testing#cards

### 2. Realistic Response Structure

The mock processor returns `AuthorizationResult` objects that match Stripe's response structure:

```python
# Success Response
AuthorizationResult(
    status=AuthStatus.AUTHORIZED,
    processor_name="mock",
    processor_auth_id="mock_pi_abc123...",      # Mirrors PaymentIntent ID
    authorization_code="123456",
    authorized_amount_cents=1000,
    currency="USD",
    authorized_at=datetime.utcnow(),
    processor_metadata={
        "payment_intent_id": "mock_pi_abc123...",
        "status": "requires_capture",           # Matches Stripe status
        "client_secret": "mock_pi_abc123..._secret_xyz",
        "charge_id": "mock_ch_def456...",
        "payment_method_id": "mock_pm_ghi789...",
        "card_brand": "visa",
        "card_last4": "4242",
    }
)

# Decline Response
AuthorizationResult(
    status=AuthStatus.DENIED,
    processor_name="mock",
    denial_code="card_declined",
    denial_reason="Your card has insufficient funds",
    processor_metadata={
        "decline_code": "insufficient_funds",   # Matches Stripe decline codes
        "payment_intent_id": "mock_pi_abc123...",
        "charge_id": "mock_ch_def456...",
    }
)
```

### 3. Configurable Behavior

```python
# Basic usage
processor = MockProcessor()

# Custom latency simulation
processor = MockProcessor(config={
    "latency_ms": 100,  # Simulate 100ms network delay
})

# Custom default response for unknown cards
processor = MockProcessor(config={
    "default_response": "authorized",  # or "declined"
})

# Custom card behaviors
processor = MockProcessor(config={
    "card_behaviors": {
        "1111111111111111": {
            "type": "success",
            "auth_code": "CUSTOM123",
        },
        "2222222222222222": {
            "type": "decline",
            "code": "card_declined",
            "decline_code": "do_not_honor",
            "reason": "Custom decline reason",
        },
    }
})
```

## Usage

### Basic Usage

```python
from auth_processor_worker.models import PaymentData
from auth_processor_worker.processors import MockProcessor

# Create processor
processor = MockProcessor()

# Create payment data
payment_data = PaymentData(
    card_number="4242424242424242",  # Success card
    exp_month=12,
    exp_year=2025,
    cvv="123",
    cardholder_name="Test User",
    billing_zip="12345",
)

# Authorize payment
result = await processor.authorize(
    payment_data=payment_data,
    amount_cents=1000,  # $10.00
    currency="USD",
    config={}
)

print(f"Status: {result.status}")  # AuthStatus.AUTHORIZED
print(f"Auth ID: {result.processor_auth_id}")  # mock_pi_...
```

### Testing Declines

```python
# Test insufficient funds decline
payment_data = PaymentData(
    card_number="4000000000009995",  # Insufficient funds
    exp_month=12,
    exp_year=2025,
    cvv="123",
    cardholder_name="Test User",
)

result = await processor.authorize(
    payment_data=payment_data,
    amount_cents=5000,
    currency="USD",
    config={}
)

assert result.status == AuthStatus.DENIED
assert result.processor_metadata["decline_code"] == "insufficient_funds"
```

### Testing Timeout/Retryable Errors

```python
from auth_processor_worker.models import ProcessorTimeout

# Test timeout scenario
payment_data = PaymentData(
    card_number="4000000000000119",  # Timeout card
    exp_month=12,
    exp_year=2025,
    cvv="123",
    cardholder_name="Test User",
)

try:
    result = await processor.authorize(
        payment_data=payment_data,
        amount_cents=1000,
        currency="USD",
        config={}
    )
except ProcessorTimeout as e:
    # This should be retried
    print(f"Timeout: {e}")
```

### Including Metadata

```python
# Include custom metadata (will be returned in processor_metadata)
result = await processor.authorize(
    payment_data=payment_data,
    amount_cents=1000,
    currency="USD",
    config={
        "metadata": {
            "order_id": "order_123",
            "customer_id": "cust_456",
        }
    }
)

# Metadata is included in response
assert result.processor_metadata["order_id"] == "order_123"
```

## Integration with Tests

### Unit Tests

See `tests/unit/test_mock_processor.py` for comprehensive unit tests covering all scenarios.

```bash
# Run mock processor unit tests
poetry run pytest tests/unit/test_mock_processor.py -v
```

### End-to-End Tests

Use the mock processor in end-to-end integration tests:

```python
import pytest
from auth_processor_worker.processors import MockProcessor

@pytest.fixture
def payment_processor():
    """Use mock processor for E2E tests."""
    return MockProcessor(config={
        "latency_ms": 10,  # Fast for tests
    })

@pytest.mark.asyncio
async def test_full_authorization_flow(payment_processor, payment_token_client):
    """Test complete auth flow from token to authorization."""
    # Create token
    token = await payment_token_client.create_token(...)

    # Decrypt payment data
    payment_data = await payment_token_client.get_payment_data(token)

    # Authorize with mock processor
    result = await payment_processor.authorize(
        payment_data=payment_data,
        amount_cents=1000,
        currency="USD",
        config={}
    )

    assert result.status == AuthStatus.AUTHORIZED
```

## Maintaining Sync with Stripe

**IMPORTANT:** The mock processor is designed to mirror Stripe's behavior. When the Stripe integration changes, the mock processor should be reviewed and updated.

### Synchronization Points

The mock processor includes detailed "SYNC POINT" comments marking areas that need to be kept synchronized with the Stripe implementation. See:

- **Response Structure**: Lines 174-189, 224-236 in `stripe_processor.py`
- **Error Handling**: Lines 208-271 in `stripe_processor.py`
- **Test Cards**: https://docs.stripe.com/testing#cards
- **Payment Method Data**: Lines 93-104 in `stripe_processor.py`

### Verification Checklist

When updating `StripeProcessor`, verify the following in `MockProcessor`:

- [ ] Test card behaviors match Stripe's latest test cards
- [ ] Response metadata fields are synchronized
- [ ] Error types and decline codes are consistent
- [ ] Authorization codes follow similar patterns
- [ ] Processor metadata keys match Stripe's structure

### Files to Review

1. `src/auth_processor_worker/processors/stripe_processor.py` - Production Stripe implementation
2. `src/auth_processor_worker/processors/mock_processor.py` - Mock implementation
3. `src/auth_processor_worker/processors/__init__.py` - Module documentation with sync notes
4. `tests/unit/test_mock_processor.py` - Unit tests
5. `tests/unit/test_stripe_processor.py` - Stripe unit tests (for comparison)

## Examples

Comprehensive usage examples are available in:

```bash
# Run examples
cd /path/to/auth-processor-worker
poetry run python examples/mock_processor_usage.py
```

See `examples/mock_processor_usage.py` for:
- Basic usage
- Decline scenarios
- Timeout handling
- Custom configuration
- Metadata inclusion
- All test card scenarios
- Custom card behaviors

## Benefits

### Fast Test Execution
- No network calls = instant responses
- Configurable latency simulation for realistic testing
- Tests run in milliseconds instead of seconds

### Deterministic Results
- Same input always produces same output
- No flaky tests due to network issues
- Reliable CI/CD pipeline

### No External Dependencies
- No Stripe API keys required
- No internet connectivity needed
- No rate limits or quotas

### Easy Error Scenario Testing
- Test rare decline codes without real cards
- Simulate timeouts and rate limits
- Test 3D Secure flows

### CI/CD Friendly
- No secrets management required
- Fast test suite execution
- Parallel test execution safe

## Limitations

The mock processor is for **testing only** and has these limitations:

1. **Not Production Ready**: Never use in production - it's for testing only
2. **No Real Card Validation**: Doesn't validate card numbers, CVV, expiry dates
3. **No Real Payment Processing**: No actual funds are authorized or captured
4. **Simplified Logic**: Some edge cases may not be fully simulated
5. **No Network Errors**: Simulates timeouts but not real network failures

## See Also

- [Stripe Test Cards Documentation](https://docs.stripe.com/testing#cards)
- [PaymentProcessor Interface](src/auth_processor_worker/processors/base.py)
- [StripeProcessor Implementation](src/auth_processor_worker/processors/stripe_processor.py)
- [Unit Tests](tests/unit/test_mock_processor.py)
- [Usage Examples](examples/mock_processor_usage.py)
