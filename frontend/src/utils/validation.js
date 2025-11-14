/**
 * Card Validation Utilities
 * Implements Luhn algorithm and other card validation logic
 */

/**
 * Validate card number using Luhn algorithm
 * @param {string} cardNumber - Card number (with or without spaces)
 * @returns {Object} Validation result with valid flag and error message
 */
export function validateCardNumber(cardNumber) {
  const cleaned = cardNumber.replace(/\s+/g, '');

  // Check length
  if (cleaned.length < 13 || cleaned.length > 19) {
    return { valid: false, error: 'Invalid card number length' };
  }

  // Check if all digits
  if (!/^\d+$/.test(cleaned)) {
    return { valid: false, error: 'Card number must contain only digits' };
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

  if (sum % 10 !== 0) {
    return { valid: false, error: 'Invalid card number (failed checksum)' };
  }

  return { valid: true };
}

/**
 * Validate expiry date
 * @param {string} month - Expiration month (1-12)
 * @param {string} year - Expiration year (full year, e.g., 2025)
 * @returns {Object} Validation result
 */
export function validateExpiry(month, year) {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  const expMonth = parseInt(month, 10);
  const expYear = parseInt(year, 10);

  if (isNaN(expMonth) || expMonth < 1 || expMonth > 12) {
    return { valid: false, error: 'Invalid month (must be 1-12)' };
  }

  if (isNaN(expYear) || expYear < currentYear) {
    return { valid: false, error: 'Card has expired' };
  }

  if (expYear === currentYear && expMonth < currentMonth) {
    return { valid: false, error: 'Card has expired' };
  }

  return { valid: true };
}

/**
 * Validate CVV
 * @param {string} cvv - CVV code (3 or 4 digits)
 * @returns {Object} Validation result
 */
export function validateCVV(cvv) {
  if (!/^\d{3,4}$/.test(cvv)) {
    return { valid: false, error: 'CVV must be 3 or 4 digits' };
  }
  return { valid: true };
}

/**
 * Validate cardholder name
 * @param {string} name - Cardholder name
 * @returns {Object} Validation result
 */
export function validateCardholderName(name) {
  if (!name || name.trim().length < 2) {
    return { valid: false, error: 'Cardholder name is required' };
  }
  return { valid: true };
}

/**
 * Validate entire payment form
 * @param {Object} formData - Form data to validate
 * @returns {Object} Validation result with errors array
 */
export function validatePaymentForm(formData) {
  const errors = [];

  const cardNumberValidation = validateCardNumber(formData.cardNumber);
  if (!cardNumberValidation.valid) {
    errors.push(cardNumberValidation.error);
  }

  const expiryValidation = validateExpiry(formData.expMonth, formData.expYear);
  if (!expiryValidation.valid) {
    errors.push(expiryValidation.error);
  }

  const cvvValidation = validateCVV(formData.cvv);
  if (!cvvValidation.valid) {
    errors.push(cvvValidation.error);
  }

  const nameValidation = validateCardholderName(formData.name);
  if (!nameValidation.valid) {
    errors.push(nameValidation.error);
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Detect card brand from card number
 * @param {string} cardNumber - Card number
 * @returns {string} Card brand (visa, mastercard, amex, discover, unknown)
 */
export function detectCardBrand(cardNumber) {
  const cleaned = cardNumber.replace(/\s+/g, '');

  if (/^4/.test(cleaned)) return 'visa';
  if (/^5[1-5]/.test(cleaned)) return 'mastercard';
  if (/^3[47]/.test(cleaned)) return 'amex';
  if (/^6(?:011|5)/.test(cleaned)) return 'discover';

  return 'unknown';
}

/**
 * Format card number with spaces every 4 digits
 * @param {string} cardNumber - Unformatted card number
 * @returns {string} Formatted card number
 */
export function formatCardNumber(cardNumber) {
  const cleaned = cardNumber.replace(/\s+/g, '');
  const formatted = cleaned.match(/.{1,4}/g);
  return formatted ? formatted.join(' ') : cleaned;
}
