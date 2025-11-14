/**
 * Validators - Utility functions for validating payment data
 */

/**
 * Validate card number using Luhn algorithm
 *
 * @param {string} cardNumber - Card number to validate
 * @returns {boolean} True if valid
 */
export function validateCardNumber(cardNumber) {
  // Remove all non-digit characters
  const cleaned = cardNumber.replace(/\D/g, '');

  // Card number should be between 13-19 digits
  if (cleaned.length < 13 || cleaned.length > 19) {
    return false;
  }

  // Luhn algorithm
  let sum = 0;
  let isEven = false;

  for (let i = cleaned.length - 1; i >= 0; i--) {
    let digit = parseInt(cleaned[i], 10);

    if (isEven) {
      digit *= 2;
      if (digit > 9) {
        digit -= 9;
      }
    }

    sum += digit;
    isEven = !isEven;
  }

  return sum % 10 === 0;
}

/**
 * Validate expiration date
 *
 * @param {string} month - Expiration month (1-12)
 * @param {string} year - Expiration year (4 digits)
 * @returns {boolean} True if valid and not expired
 */
export function validateExpiry(month, year) {
  const monthNum = parseInt(month, 10);
  const yearNum = parseInt(year, 10);

  // Validate month range
  if (monthNum < 1 || monthNum > 12) {
    return false;
  }

  // Validate year format
  if (year.length !== 4 || yearNum < 2000) {
    return false;
  }

  // Check if expired
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  if (yearNum < currentYear) {
    return false;
  }

  if (yearNum === currentYear && monthNum < currentMonth) {
    return false;
  }

  return true;
}

/**
 * Validate CVV code
 *
 * @param {string} cvv - CVV code
 * @param {string} cardBrand - Card brand (optional, for amex detection)
 * @returns {boolean} True if valid
 */
export function validateCVV(cvv, cardBrand = null) {
  // Remove all non-digit characters
  const cleaned = cvv.replace(/\D/g, '');

  // Amex uses 4 digits, others use 3
  if (cardBrand === 'amex') {
    return cleaned.length === 4;
  }

  return cleaned.length === 3;
}

/**
 * Validate email address
 *
 * @param {string} email - Email address to validate
 * @returns {boolean} True if valid
 */
export function validateEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Validate all card details
 *
 * @param {Object} cardDetails - Card details object
 * @returns {Object} Validation result with errors
 */
export function validateCardDetails(cardDetails) {
  const errors = {};

  if (!validateCardNumber(cardDetails.cardNumber)) {
    errors.cardNumber = 'Invalid card number';
  }

  if (!validateExpiry(cardDetails.expMonth, cardDetails.expYear)) {
    errors.expiry = 'Invalid or expired date';
  }

  if (!validateCVV(cardDetails.cvv)) {
    errors.cvv = 'Invalid CVV';
  }

  if (cardDetails.email && !validateEmail(cardDetails.email)) {
    errors.email = 'Invalid email address';
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors
  };
}
