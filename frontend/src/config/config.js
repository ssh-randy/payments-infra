export const CONFIG = {
  RESTAURANT_ID: '12345678-1234-5678-1234-567812345678',

  // Service URLs (configurable for local vs deployed)
  PAYMENT_TOKEN_SERVICE_URL: import.meta.env.VITE_PAYMENT_TOKEN_SERVICE_URL || 'http://localhost:8001',
  AUTHORIZATION_API_URL: import.meta.env.VITE_AUTHORIZATION_API_URL || 'http://localhost:8000',

  // API Partner Encryption Key
  API_PARTNER_KEY_ID: 'demo-primary-key-001',

  // Tax rate
  TAX_RATE: 0.09,  // 9%

  // Polling config
  STATUS_POLL_INTERVAL_MS: 1000,
  STATUS_POLL_TIMEOUT_MS: 30000,

  // Feature flags
  ENABLE_STRIPE_DASHBOARD_LINKS: true,
  ENABLE_DEBUG_MODE: false
};
