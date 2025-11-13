# Stripe Integration Test Setup

## Current Status

✅ **Stripe integration tests with tokens are working** (8 tests passing)
⏳ **Raw card data tests blocked** - Waiting for Stripe support approval

## Why Raw Card Data Tests Are Blocked

The Stripe integration tests are **correctly calling the real Stripe API**, but Stripe is blocking raw card data for new test accounts:

```
"Sending credit card numbers directly to the Stripe API is generally unsafe.
We suggest you use test tokens that map to the test card you are using."
```

## Why We Need Raw Card Data Access

Our architecture requires sending raw card data to Stripe because:

1. **Payment Token Service** decrypts payment tokens → raw card data
2. **Auth Processor Worker** receives decrypted card data → sends to Stripe
3. This is a **backend-to-backend** flow (no frontend tokenization)

This is intentional and secure because:
- Card data never touches frontend or API layer
- Only PCI-scoped services handle raw card data
- Data is in memory only, never logged or persisted

## How to Enable Raw Card Data API

### Step 1: Find the Setting

1. Go to: **https://dashboard.stripe.com/acct_1SRf3sImz3HRJCSc/account/integration/settings**
2. Or navigate: **Stripe Dashboard** → **Settings** → **Integration** → **Settings**
3. Look for section: **"Raw card data access"**
4. You'll see a toggle that is **disabled** (cannot be enabled yet)

### Step 2: Meet Requirements

The toggle cannot be enabled until you meet these requirements:
https://support.stripe.com/questions/enabling-access-to-raw-card-data-apis

**Requirements:**
- Contact Stripe support
- Explain this is a **testing-only account**
- Provide details about your PCI-compliant backend architecture
- Wait for approval (can take several days)

### Step 3: Contact Support

**We have already contacted Stripe support (as of 2025-11-11)** to request approval for testing purposes.

**Status:** ⏳ Waiting for response

## Alternative: Test with Stripe Tokens (Currently Working)

**We created alternative integration tests that use Stripe test tokens:**

```bash
# Run token-based integration tests (8 tests, all passing)
poetry run pytest tests/integration/test_stripe_with_tokens.py -m integration -v
```

**What these tests validate:**
- ✅ Stripe PaymentIntent API integration
- ✅ Authorization-only (capture_method='manual')
- ✅ Capture flow
- ✅ Void/cancel flow
- ✅ Card declines and error handling
- ✅ Metadata preservation
- ✅ Multi-currency support

**Test tokens used:**
- `pm_card_visa` - Successful Visa card
- `pm_card_mastercard` - Successful Mastercard
- `pm_card_chargeDeclined` - Always declines
- `pm_card_chargeDeclinedInsufficientFunds` - Insufficient funds

**Note:** These tests validate the Stripe integration but don't test the full flow with raw card data from Payment Token Service. That requires raw card data API access.

## Test Status Summary

| Test Suite | Status | What It Tests |
|------------|--------|---------------|
| `test_stripe_with_tokens.py` | ✅ **8/8 passing** | Stripe API integration with test tokens |
| `test_stripe_real_api.py` | ⏳ **Blocked** | Full flow with raw card data (needs approval) |
| `test_payment_token_client.py` | ✅ **25/25 passing** | Payment Token Service client (with mocks) |
| `test_stripe_processor.py` | ✅ **15/15 passing** | Stripe processor unit tests (with mocks) |

**Total: 48 tests passing, 12 tests blocked on Stripe approval**

## Production Considerations

In production:
- Raw card data API access is **not** blocked
- Stripe allows backend services to send card data via their API
- This is a standard pattern for payment gateways
- PCI compliance is achieved through proper scoping and access controls

## Next Steps (After Approval)

1. ✅ **Stripe approves raw card data access** (waiting...)
2. ✅ Enable toggle at: https://dashboard.stripe.com/acct_1SRf3sImz3HRJCSc/account/integration/settings
3. ✅ Run raw card data tests: `poetry run pytest tests/integration/test_stripe_real_api.py -m integration`
4. ✅ Verify authorizations in Stripe dashboard

## For Now: Use Token-Based Tests

```bash
# These work right now and validate Stripe integration
poetry run pytest tests/integration/test_stripe_with_tokens.py -m integration -v
```

After approval, we'll have **full end-to-end testing** with raw card data flow.
