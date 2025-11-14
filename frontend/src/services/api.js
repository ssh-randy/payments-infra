import { CONFIG } from '../config/config';

/**
 * API Service - Handles communication with backend services
 * Stub functions to be implemented in:
 * - i-82kx: createPaymentToken implementation
 * - i-5xjm: authorizePayment and pollPaymentStatus implementation
 */

/**
 * Create a payment token from card details
 * To be implemented in i-82kx
 *
 * @param {Object} cardDetails - Card information
 * @param {string} cardDetails.cardNumber - Card number
 * @param {string} cardDetails.expMonth - Expiration month
 * @param {string} cardDetails.expYear - Expiration year
 * @param {string} cardDetails.cvv - CVV code
 * @returns {Promise<Object>} Payment token response
 */
export async function createPaymentToken(cardDetails) {
  console.log('[API] createPaymentToken called with:', {
    cardNumber: '****' + cardDetails.cardNumber.slice(-4),
    expMonth: cardDetails.expMonth,
    expYear: cardDetails.expYear
  });

  // Stub implementation - to be replaced in i-82kx
  return {
    paymentToken: 'stub_payment_token_' + Date.now(),
    tokenId: 'stub_token_id_' + Date.now()
  };
}

/**
 * Authorize a payment using a payment token
 * To be implemented in i-5xjm
 *
 * @param {Object} paymentData - Payment information
 * @param {string} paymentData.paymentToken - Payment token from createPaymentToken
 * @param {number} paymentData.amount - Amount in cents
 * @param {string} paymentData.currency - Currency code (e.g., 'USD')
 * @param {string} paymentData.email - Customer email
 * @param {string} paymentData.restaurantId - Restaurant ID
 * @returns {Promise<Object>} Authorization response
 */
export async function authorizePayment(paymentData) {
  console.log('[API] authorizePayment called with:', {
    paymentToken: paymentData.paymentToken,
    amount: paymentData.amount,
    currency: paymentData.currency,
    email: paymentData.email
  });

  // Stub implementation - to be replaced in i-5xjm
  return {
    paymentIntentId: 'pi_stub_' + Date.now(),
    status: 'processing'
  };
}

/**
 * Poll payment status until completion
 * To be implemented in i-5xjm
 *
 * @param {string} paymentIntentId - Payment Intent ID
 * @returns {Promise<Object>} Payment status
 */
export async function pollPaymentStatus(paymentIntentId) {
  console.log('[API] pollPaymentStatus called for:', paymentIntentId);

  // Stub implementation - to be replaced in i-5xjm
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        status: 'succeeded',
        paymentIntentId: paymentIntentId,
        chargeId: 'ch_stub_' + Date.now()
      });
    }, 2000);
  });
}

/**
 * Get Stripe Dashboard link for a payment
 *
 * @param {string} paymentIntentId - Payment Intent ID
 * @returns {string} Dashboard URL
 */
export function getStripeDashboardLink(paymentIntentId) {
  if (!CONFIG.ENABLE_STRIPE_DASHBOARD_LINKS) {
    return null;
  }

  // This will be updated with actual Stripe account ID
  return `https://dashboard.stripe.com/test/payments/${paymentIntentId}`;
}
