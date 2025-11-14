import { CONFIG } from '../config/config';
import { detectCardBrand } from '../utils/validation';

/**
 * Encryption Service - Handles client-side encryption for API Partner Key flow
 *
 * ⚠️ WARNING: This implementation encrypts card data in the browser for DEMO purposes only!
 * This is NOT secure for production:
 * - Browser JavaScript can be inspected/modified
 * - Encryption keys can be extracted from browser code
 * - No protection against XSS attacks
 *
 * Production systems should:
 * - Use Stripe Elements (card data goes directly to Stripe)
 * - OR collect card data server-side over HTTPS
 * - NEVER expose encryption keys in client-side code
 */

/**
 * Derive encryption key from master key using PBKDF2
 * @param {string} masterKey - Demo master key
 * @param {string} keyId - API Partner Key ID
 * @returns {Promise<CryptoKey>} Derived encryption key
 */
async function deriveEncryptionKey(masterKey, keyId) {
  const encoder = new TextEncoder();

  // Import master key material
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(masterKey),
    { name: 'PBKDF2' },
    false,
    ['deriveKey']
  );

  // Derive AES-GCM key
  return await crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: encoder.encode(keyId),
      iterations: 100000,
      hash: 'SHA-256'
    },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt']
  );
}

/**
 * Get encryption key for API Partner
 * In production, this would fetch from a secure key server
 * For demo, we derive from a hardcoded master key
 *
 * @param {string} keyId - API Partner Key ID
 * @returns {Promise<CryptoKey>} Encryption key
 */
export async function getApiPartnerEncryptionKey(keyId) {
  // DEMO IMPLEMENTATION: Use hardcoded primary key
  // Production: Fetch from secure key server

  if (keyId === 'demo-primary-key-001') {
    // Derive from master key for demo
    const mockMasterKey = 'demo-master-key-not-for-production';
    return await deriveEncryptionKey(mockMasterKey, keyId);
  }

  throw new Error(`Unknown key_id: ${keyId}`);
}

/**
 * Convert ArrayBuffer to Base64 string
 * @param {ArrayBuffer} arrayBuffer - Data to encode
 * @returns {string} Base64 encoded string
 */
function base64Encode(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Encrypt card data using AES-GCM
 * @param {Object} cardData - Card details to encrypt
 * @param {string} cardData.cardNumber - Card number
 * @param {string} cardData.expMonth - Expiration month
 * @param {string} cardData.expYear - Expiration year
 * @param {string} cardData.cvv - CVV code
 * @param {string} cardData.name - Cardholder name
 * @param {CryptoKey} key - Encryption key
 * @param {string} keyId - API Partner Key ID
 * @returns {Promise<Object>} Encrypted data with IV and metadata
 */
async function encryptCardData(cardData, key, keyId) {
  const encoder = new TextEncoder();

  // Prepare plaintext - card data as JSON
  const plaintext = JSON.stringify({
    card_number: cardData.cardNumber.replace(/\s+/g, ''),
    exp_month: cardData.expMonth,
    exp_year: cardData.expYear,
    cvv: cardData.cvv,
    cardholder_name: cardData.name
  });

  // Generate random IV (12 bytes for AES-GCM)
  const iv = crypto.getRandomValues(new Uint8Array(12));

  // Encrypt using AES-GCM
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoder.encode(plaintext)
  );

  return {
    encrypted,
    iv,
    keyId
  };
}

/**
 * Encrypt card details using API Partner Key
 * This is the main function called by the checkout flow
 *
 * @param {Object} cardDetails - Card information to encrypt
 * @param {string} cardDetails.cardNumber - Card number
 * @param {string} cardDetails.expMonth - Expiration month
 * @param {string} cardDetails.expYear - Expiration year
 * @param {string} cardDetails.cvv - CVV code
 * @param {string} cardDetails.name - Cardholder name
 * @returns {Promise<Object>} Encrypted card data ready for Payment Token Service
 */
export async function encryptCardDetails(cardDetails) {
  console.log('[Encryption] Encrypting card details with key ID:', CONFIG.API_PARTNER_KEY_ID);

  try {
    // 1. Get encryption key for this API partner
    const encryptionKey = await getApiPartnerEncryptionKey(CONFIG.API_PARTNER_KEY_ID);

    // 2. Encrypt card data
    const { encrypted, iv, keyId } = await encryptCardData(
      cardDetails,
      encryptionKey,
      CONFIG.API_PARTNER_KEY_ID
    );

    // 3. Return encrypted data with metadata for Payment Token Service
    return {
      encrypted_payment_data: base64Encode(encrypted),
      encryption_metadata: {
        key_id: keyId,
        algorithm: 'AES-256-GCM',
        iv: base64Encode(iv)
      },
      metadata: {
        card_brand: detectCardBrand(cardDetails.cardNumber),
        last4: cardDetails.cardNumber.replace(/\s+/g, '').slice(-4),
        source: 'online_ordering'
      }
    };
  } catch (error) {
    console.error('[Encryption] Error encrypting card details:', error);
    throw new Error('Failed to encrypt card data: ' + error.message);
  }
}

/**
 * Generate a UUID v4
 * Used for idempotency keys
 * @returns {string} UUID string
 */
export function generateUUID() {
  return crypto.randomUUID();
}
