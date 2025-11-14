import { CONFIG } from '../config/config';
import { encryptCardDetails, generateUUID } from './encryption';

/**
 * API Service - Handles communication with backend services
 */

/**
 * Create a payment token from card details
 * Implements the full flow:
 * 1. Encrypt card data using API partner key
 * 2. Send encrypted data to Payment Token Service
 * 3. Return payment token
 *
 * @param {Object} cardDetails - Card information
 * @param {string} cardDetails.cardNumber - Card number
 * @param {string} cardDetails.expMonth - Expiration month
 * @param {string} cardDetails.expYear - Expiration year
 * @param {string} cardDetails.cvv - CVV code
 * @param {string} cardDetails.name - Cardholder name
 * @returns {Promise<Object>} Payment token response
 */
export async function createPaymentToken(cardDetails) {
  console.log('[API] createPaymentToken called with:', {
    cardNumber: '****' + cardDetails.cardNumber.slice(-4),
    expMonth: cardDetails.expMonth,
    expYear: cardDetails.expYear
  });

  try {
    // Step 1: Encrypt card data
    console.log('[API] Encrypting card data...');
    const encryptedData = await encryptCardDetails(cardDetails);

    // Step 2: Create payment token via API
    console.log('[API] Calling Payment Token Service...');
    const response = await fetch(
      `${CONFIG.PAYMENT_TOKEN_SERVICE_URL}/v1/payment-tokens`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer test-api-key-12345',
          'X-Idempotency-Key': generateUUID()
        },
        body: JSON.stringify({
          restaurant_id: CONFIG.RESTAURANT_ID,
          encrypted_payment_data: encryptedData.encrypted_payment_data,
          encryption_metadata: encryptedData.encryption_metadata,
          metadata: encryptedData.metadata
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      console.error('[API] Payment Token Service error:', error);
      throw new Error(error.detail || 'Failed to create payment token');
    }

    const result = await response.json();
    console.log('[API] Payment token created successfully:', result.payment_token);

    return {
      paymentToken: result.payment_token,
      tokenId: result.token_id || result.payment_token
    };

  } catch (error) {
    console.error('[API] Error creating payment token:', error);
    throw new Error('Failed to create payment token: ' + error.message);
  }
}

/**
 * Authorize a payment using a payment token
 *
 * @param {string} paymentToken - Payment token from createPaymentToken
 * @param {number} amountCents - Amount in cents
 * @param {Object} metadata - Optional metadata (cart items, order info)
 * @returns {Promise<string>} Authorization request ID
 */
export async function authorizePayment(paymentToken, amountCents, metadata = {}) {
  console.log('[API] authorizePayment called with:', {
    paymentToken: paymentToken,
    amountCents: amountCents,
    metadata: metadata
  });

  try {
    const idempotencyKey = generateUUID();

    console.log('[API] Calling Authorization API...');
    const response = await fetch(
      `${CONFIG.AUTHORIZATION_API_URL}/v1/authorize`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': idempotencyKey
        },
        body: JSON.stringify({
          restaurant_id: CONFIG.RESTAURANT_ID,
          payment_token: paymentToken,
          amount_cents: amountCents,
          currency: 'USD',
          idempotency_key: idempotencyKey,
          metadata: {
            order_source: 'frontend_demo',
            ...metadata
          }
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      console.error('[API] Authorization API error:', error);
      throw new Error(error.detail || 'Failed to authorize payment');
    }

    const result = await response.json();
    console.log('[API] Authorization request created:', result.auth_request_id);

    return result.auth_request_id;

  } catch (error) {
    console.error('[API] Error authorizing payment:', error);
    throw error;
  }
}

/**
 * Helper function to sleep for a given number of milliseconds
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Poll payment status until completion or timeout
 *
 * @param {string} authRequestId - Authorization request ID
 * @returns {Promise<Object>} Payment status
 */
export async function pollPaymentStatus(authRequestId) {
  console.log('[API] pollPaymentStatus called for:', authRequestId);

  const startTime = Date.now();
  const timeout = CONFIG.STATUS_POLL_TIMEOUT_MS;
  const pollInterval = CONFIG.STATUS_POLL_INTERVAL_MS;

  while (Date.now() - startTime < timeout) {
    try {
      console.log('[API] Polling status for:', authRequestId);
      const response = await fetch(
        `${CONFIG.AUTHORIZATION_API_URL}/v1/authorize/${authRequestId}/status?restaurant_id=${CONFIG.RESTAURANT_ID}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) {
        console.warn('[API] Failed to fetch payment status, will retry...');
        await sleep(pollInterval);
        continue;
      }

      const status = await response.json();
      console.log('[API] Current status:', status.status);

      // Check if terminal state
      if (['AUTHORIZED', 'DENIED', 'FAILED'].includes(status.status)) {
        console.log('[API] Payment reached terminal state:', status.status);
        return status;
      }

      // Wait before next poll
      await sleep(pollInterval);

    } catch (error) {
      console.error('[API] Error polling status:', error);
      // Continue polling on transient errors
      await sleep(pollInterval);
    }
  }

  throw new Error('Payment status polling timeout');
}

/**
 * Get Stripe Dashboard link for a payment
 *
 * @param {string} processorAuthId - Processor authorization ID (e.g., Stripe charge ID)
 * @returns {string|null} Dashboard URL or null if disabled/invalid
 */
export function getStripeDashboardLink(processorAuthId) {
  if (!CONFIG.ENABLE_STRIPE_DASHBOARD_LINKS) {
    return null;
  }

  // Check if it's a Stripe charge ID (starts with 'ch_' or 'pi_')
  if (processorAuthId && (processorAuthId.startsWith('ch_') || processorAuthId.startsWith('pi_'))) {
    return `https://dashboard.stripe.com/test/payments/${processorAuthId}`;
  }

  return null;
}
