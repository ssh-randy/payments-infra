/**
 * Formatters - Utility functions for formatting data
 */

/**
 * Format a number as currency
 *
 * @param {number} amount - Amount to format
 * @param {string} currency - Currency code (default: 'USD')
 * @returns {string} Formatted currency string
 */
export function formatCurrency(amount, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency
  }).format(amount);
}

/**
 * Format card number with spacing
 *
 * @param {string} cardNumber - Card number to format
 * @returns {string} Formatted card number (e.g., "4242 4242 4242 4242")
 */
export function formatCardNumber(cardNumber) {
  // Remove all non-digit characters
  const cleaned = cardNumber.replace(/\D/g, '');

  // Add spaces every 4 digits
  const formatted = cleaned.match(/.{1,4}/g)?.join(' ') || '';

  return formatted;
}

/**
 * Detect card brand from card number
 *
 * @param {string} cardNumber - Card number
 * @returns {string} Card brand (visa, mastercard, amex, discover, unknown)
 */
export function detectCardBrand(cardNumber) {
  const cleaned = cardNumber.replace(/\D/g, '');

  if (/^4/.test(cleaned)) {
    return 'visa';
  } else if (/^5[1-5]/.test(cleaned)) {
    return 'mastercard';
  } else if (/^3[47]/.test(cleaned)) {
    return 'amex';
  } else if (/^6(?:011|5)/.test(cleaned)) {
    return 'discover';
  }

  return 'unknown';
}

/**
 * Mask card number (show only last 4 digits)
 *
 * @param {string} cardNumber - Card number to mask
 * @returns {string} Masked card number (e.g., "**** **** **** 4242")
 */
export function maskCardNumber(cardNumber) {
  const cleaned = cardNumber.replace(/\D/g, '');
  if (cleaned.length < 4) {
    return cardNumber;
  }

  const lastFour = cleaned.slice(-4);
  return '**** **** **** ' + lastFour;
}

/**
 * Format expiration date
 *
 * @param {string} month - Expiration month
 * @param {string} year - Expiration year
 * @returns {string} Formatted expiration (e.g., "12/2025")
 */
export function formatExpiration(month, year) {
  const paddedMonth = month.padStart(2, '0');
  return `${paddedMonth}/${year}`;
}

/**
 * Format currency from cents
 *
 * @param {number} cents - Amount in cents
 * @returns {string} Formatted currency string (e.g., "$14.00")
 */
export function formatCurrencyCents(cents) {
  return formatCurrency(cents / 100);
}

/**
 * Generate a UUID v4
 *
 * @returns {string} UUID string
 */
export function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}
