# Stripe Processor Integration - Setup and Testing Guide

## Overview

This document provides guidance on setting up and testing the Stripe payment processor integration for the Auth Processor Worker Service.

## API Approach Decision

### Payment Intents API vs Charges API

We have implemented the **Payment Intents API** with manual capture for the following reasons:

1. **Modern Best Practice**: Payment Intents is Stripe's recommended API for all new integrations (as of 2025)
2. **Better Success Rates**: 97.4% success rate after authentication vs 84% with legacy Charges API
3. **SCA Ready**: Built-in support for Strong Customer Authentication (3D Secure, etc.)
4. **Future-Proof**: New features are only added to Payment Intents API

### How Authorization Works

The integration uses `capture_method='manual'` when creating PaymentIntents:

```python
stripe.PaymentIntent.create(
    amount=amount_cents,
    currency=currency,
    capture_method='manual',  # Authorization only
    confirm=True,             # Confirm immediately
    ...
)
```

When successful, the PaymentIntent status becomes `requires_capture`, indicating funds are authorized but not captured.

## Stripe Test Environment Setup

### 1. Create a Stripe Account

1. Go to [https://stripe.com/](https://stripe.com/)
2. Sign up for a free account
3. Complete email verification

### 2. Obtain API Keys

1. Log into the Stripe Dashboard
2. Switch to **Test Mode** (toggle in the top right)
3. Navigate to **Developers** → **API Keys**
4. Copy your **Secret Key** (starts with `sk_test_...`)
5. Keep this key secure - it will be used for testing

### 3. Configure Environment Variables

Create a `.env` file in the `services/auth-processor-worker/` directory:

```bash
# Stripe Configuration
STRIPE__API_KEY=sk_test_YOUR_SECRET_KEY_HERE
STRIPE__TIMEOUT_SECONDS=10

# Other required settings
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/payment_events
WORKER__SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/your-queue-url
AWS_REGION=us-east-1
ENVIRONMENT=development
DEBUG=true
```

## Test Card Numbers

Stripe provides test card numbers for different scenarios:

### Successful Authorization
- **4242 4242 4242 4242** - Visa (always succeeds)
- **5555 5555 5555 4444** - Mastercard (always succeeds)
- **3782 822463 10005** - American Express (always succeeds)

### Specific Declines
- **4000 0000 0000 0002** - Card declined (generic)
- **4000 0000 0000 9995** - Insufficient funds
- **4000 0000 0000 0069** - Expired card
- **4000 0000 0000 0127** - Incorrect CVC
- **4000 0000 0000 0119** - Processing error

### 3D Secure / Authentication
- **4000 0027 6000 3184** - Requires authentication (3DS)
- **4000 0082 6000 3178** - Requires authentication (declined after auth)

### Rate Limiting
- **4000 0000 0000 0341** - Triggers rate limiting errors

**For all test cards:**
- Use any future expiration date (e.g., 12/2025)
- Use any 3-digit CVC (e.g., 123)
- Use any cardholder name and zip code

Full list: [https://stripe.com/docs/testing](https://stripe.com/docs/testing)

## Running Tests

### Unit Tests (Mocked Stripe API)

The unit tests use mocked Stripe responses and don't require a real Stripe account:

```bash
cd services/auth-processor-worker
poetry install
poetry run pytest tests/unit/test_stripe_processor.py -v
```

These tests cover:
- Successful authorizations
- Card declines (insufficient funds, expired, etc.)
- Error handling (rate limits, API errors, timeouts)
- Configuration handling (metadata, statement descriptors)

### Integration Tests (Real Stripe API)

For integration tests that call the real Stripe API:

```bash
# Ensure STRIPE__API_KEY is set in your environment
export STRIPE__API_KEY=sk_test_YOUR_KEY_HERE

# Run integration tests
poetry run pytest tests/integration/ -v -m integration
```

**Note**: Integration tests will create actual authorization requests in your Stripe test account (they will not capture funds).

## Error Handling

### Retryable Errors (ProcessorTimeout)

These errors trigger retry logic with exponential backoff:

- **Rate Limit Errors (429)**: Too many requests
- **API Errors (5xx)**: Stripe server issues
- **Connection Errors**: Network timeouts, connection failures
- **Invalid Request Errors**: May be due to temporary config issues

### Terminal Errors (No Retry)

These return immediately without retry:

- **Card Declines**: Insufficient funds, expired card, etc. (returns `AuthStatus.DENIED`)
- **Authentication Required**: 3D Secure challenges (returns `AuthStatus.DENIED`)

### Error Classification Example

```python
try:
    result = await processor.authorize(...)
    if result.status == AuthStatus.AUTHORIZED:
        # Success! Capture later
    elif result.status == AuthStatus.DENIED:
        # Card declined - normal business outcome
        # Check result.denial_code and result.denial_reason
except ProcessorTimeout:
    # Transient error - retry with backoff
```

## Authorization Validity

Authorized funds have time limits before they expire:

- **Visa**: 5-7 days (depending on type)
- **Mastercard/Amex/Discover**: 7 days
- **Japan (JPY)**: Up to 30 days for eligible cards

After expiration, the authorization is automatically released and you must re-authorize.

## Production Considerations

### 1. Switch to Live Mode

When moving to production:

1. Obtain your **live API key** from Stripe Dashboard (starts with `sk_live_...`)
2. Update your production environment variables
3. Test with small real transactions first
4. Ensure your Stripe account is fully activated

### 2. Handle 3D Secure

The current implementation returns `DENIED` for payments requiring 3D Secure. For production:

1. Implement a more sophisticated flow (redirect to 3DS challenge)
2. Consider using Stripe Checkout or Elements for frontend handling
3. Or use server-side confirmation with `return_url` for redirect-based authentication

### 3. Webhook Integration

Consider setting up webhooks to handle:

- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `charge.expired` (authorization expired without capture)

### 4. Monitoring

Key metrics to monitor:

- Authorization success rate
- Decline rate by decline_code
- Rate limit errors (indicates scaling needs)
- API error rates
- Authorization expiry rate (indicates capture delays)

## Troubleshooting

### "Invalid API Key" Errors

- Ensure you're using the correct key for your environment (test vs live)
- Verify the key starts with `sk_test_` (for test mode)
- Check that the key is properly set in your `.env` file

### "No Such PaymentIntent" Errors

- The PaymentIntent ID may be invalid or from a different account
- Ensure you're using the same API key that created the intent

### Rate Limiting

- Stripe's test mode has rate limits (100 requests per second)
- Implement exponential backoff for retries
- Consider request throttling for high-volume scenarios

### Authorization Expires Too Quickly

- Check your capture timing - ensure you capture before expiry
- Consider using Stripe's `automatic_delayed` capture mode
- Monitor the `authorization_expires_at` field

## Resources

- [Stripe API Reference](https://stripe.com/docs/api)
- [Payment Intents Guide](https://stripe.com/docs/payments/payment-intents)
- [Place a Hold (Authorization)](https://stripe.com/docs/payments/place-a-hold-on-a-payment-method)
- [Test Cards](https://stripe.com/docs/testing)
- [Error Codes](https://stripe.com/docs/error-codes)
- [Decline Codes](https://stripe.com/docs/declines/codes)
