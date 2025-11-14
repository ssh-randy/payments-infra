import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import Header from '../components/Header';
import Footer from '../components/Footer';
import LoadingSpinner from '../components/LoadingSpinner';
import { CONFIG } from '../config/config';
import { createPaymentToken, authorizePayment, pollPaymentStatus } from '../services/api';
import { validatePaymentForm, formatCardNumber } from '../utils/validation';

/**
 * CheckoutPage - Payment form page
 * Implements payment form with card data encryption and token creation (i-82kx)
 */
function CheckoutPage() {
  const navigate = useNavigate();
  const { cartItems, calculateTotals } = useCart();

  const [isProcessing, setIsProcessing] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState('');
  const [formData, setFormData] = React.useState({
    cardNumber: '',
    expMonth: '',
    expYear: '',
    cvv: '',
    email: '',
    name: ''
  });

  // Calculate totals from cart
  const { subtotal_cents, tax_cents, total_cents } = calculateTotals();
  const subtotal = subtotal_cents / 100;
  const tax = tax_cents / 100;
  const total = total_cents / 100;

  const handleInputChange = (e) => {
    const { name, value } = e.target;

    // Auto-format card number
    if (name === 'cardNumber') {
      const formatted = formatCardNumber(value);
      setFormData(prev => ({ ...prev, [name]: formatted }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }

    // Clear error message when user starts typing
    if (errorMessage) {
      setErrorMessage('');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsProcessing(true);
    setErrorMessage('');

    try {
      // Step 1: Validate form
      console.log('[CheckoutPage] Validating form data...');
      const validation = validatePaymentForm(formData);
      if (!validation.valid) {
        setErrorMessage(validation.errors.join(', '));
        setIsProcessing(false);
        return;
      }

      // Step 2: Create payment token
      console.log('[CheckoutPage] Creating payment token...');
      const tokenResponse = await createPaymentToken({
        cardNumber: formData.cardNumber,
        expMonth: formData.expMonth,
        expYear: formData.expYear,
        cvv: formData.cvv,
        name: formData.name
      });

      console.log('[CheckoutPage] Payment token created:', tokenResponse.paymentToken);

      // Step 3: Submit authorization request
      console.log('[CheckoutPage] Submitting authorization request...');
      const cartItemsMetadata = cartItems.map(item => ({
        name: item.name,
        quantity: item.quantity,
        unit_price_cents: item.unit_price_cents
      }));

      const authRequestId = await authorizePayment(
        tokenResponse.paymentToken,
        total_cents,
        {
          cart_items: cartItemsMetadata,
          customer_email: formData.email
        }
      );

      console.log('[CheckoutPage] Authorization request submitted:', authRequestId);

      // Step 4: Navigate to status page and poll for result
      navigate('/status', {
        state: {
          authRequestId: authRequestId,
          totalCents: total_cents
        }
      });

    } catch (error) {
      console.error('[CheckoutPage] Error during checkout:', error);
      setErrorMessage(error.message || 'Failed to process payment. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  if (cartItems.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Header />
        <main style={{ flex: 1, padding: '2rem', textAlign: 'center' }}>
          <h2>No items in cart</h2>
          <p>Please add items to your cart before checking out.</p>
          <button
            onClick={() => navigate('/')}
            style={{
              backgroundColor: '#3498db',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              padding: '0.75rem 1.5rem',
              cursor: 'pointer',
              fontWeight: 'bold',
              marginTop: '1rem'
            }}
          >
            Back to Menu
          </button>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />

      <main style={{
        flex: 1,
        maxWidth: '800px',
        width: '100%',
        margin: '0 auto',
        padding: '2rem'
      }}>
        <h2 style={{ color: '#333' }}>Checkout</h2>

        <div style={{
          backgroundColor: '#f8f9fa',
          padding: '1rem',
          borderRadius: '8px',
          marginBottom: '2rem',
          color: '#333'
        }}>
          <h3 style={{ marginTop: 0, color: '#333' }}>Order Summary</h3>
          {cartItems.map((item, index) => (
            <div key={index} style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '0.5rem 0',
              borderBottom: '1px solid #ddd',
              color: '#333'
            }}>
              <span>{item.name} x{item.quantity}</span>
              <span>${(item.subtotal_cents / 100).toFixed(2)}</span>
            </div>
          ))}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '0.5rem 0',
            marginTop: '0.5rem',
            color: '#333'
          }}>
            <span>Subtotal:</span>
            <span>${subtotal.toFixed(2)}</span>
          </div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '0.5rem 0',
            color: '#333'
          }}>
            <span>Tax (9%):</span>
            <span>${tax.toFixed(2)}</span>
          </div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: '1rem',
            fontWeight: 'bold',
            fontSize: '1.2rem',
            paddingTop: '0.5rem',
            borderTop: '2px solid #333',
            color: '#333'
          }}>
            <span>Total:</span>
            <span>${total.toFixed(2)}</span>
          </div>
        </div>

        {isProcessing ? (
          <LoadingSpinner message="Processing payment..." />
        ) : (
          <>
            {/* Test Cards Information */}
            <div style={{
              backgroundColor: '#fff3cd',
              padding: '1rem',
              borderRadius: '8px',
              marginBottom: '2rem',
              border: '1px solid #ffc107',
              color: '#856404'
            }}>
              <h4 style={{ marginTop: 0, marginBottom: '0.5rem', color: '#856404' }}>🧪 Test Cards</h4>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.9rem', color: '#856404' }}>
                <li><strong>4242 4242 4242 4242</strong> - Success</li>
                <li><strong>4000 0000 0000 9995</strong> - Declined (insufficient funds)</li>
                <li><strong>4000 0000 0000 0002</strong> - Declined (card declined)</li>
              </ul>
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', fontStyle: 'italic', color: '#856404' }}>
                Use any future date for expiry and any 3-4 digit CVV
              </p>
            </div>

            <form onSubmit={handleSubmit} style={{
              backgroundColor: 'white',
              padding: '2rem',
              borderRadius: '8px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
              <h3 style={{ marginTop: 0, color: '#333' }}>Payment Information</h3>

              {/* Error Message */}
              {errorMessage && (
                <div style={{
                  backgroundColor: '#f8d7da',
                  color: '#721c24',
                  padding: '1rem',
                  borderRadius: '4px',
                  marginBottom: '1rem',
                  border: '1px solid #f5c6cb'
                }}>
                  <strong>Error:</strong> {errorMessage}
                </div>
              )}

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                  Cardholder Name *
                </label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  placeholder="John Doe"
                  required
                  autoComplete="cc-name"
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '1rem'
                  }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                  Email *
                </label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  placeholder="john@example.com"
                  required
                  autoComplete="email"
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '1rem'
                  }}
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                  Card Number *
                </label>
                <input
                  type="text"
                  name="cardNumber"
                  value={formData.cardNumber}
                  onChange={handleInputChange}
                  placeholder="4242 4242 4242 4242"
                  required
                  maxLength="19"
                  autoComplete="cc-number"
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '1rem',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                    Month *
                  </label>
                  <input
                    type="text"
                    name="expMonth"
                    value={formData.expMonth}
                    onChange={handleInputChange}
                    placeholder="12"
                    required
                    maxLength="2"
                    autoComplete="cc-exp-month"
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '1rem'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                    Year *
                  </label>
                  <input
                    type="text"
                    name="expYear"
                    value={formData.expYear}
                    onChange={handleInputChange}
                    placeholder="2025"
                    required
                    maxLength="4"
                    autoComplete="cc-exp-year"
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '1rem'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold', color: '#333' }}>
                    CVV *
                  </label>
                  <input
                    type="text"
                    name="cvv"
                    value={formData.cvv}
                    onChange={handleInputChange}
                    placeholder="123"
                    required
                    maxLength="4"
                    autoComplete="cc-csc"
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '1rem'
                    }}
                  />
                </div>
              </div>

              {/* Security Notice */}
              <div style={{
                backgroundColor: '#f0f0f0',
                padding: '0.75rem',
                borderRadius: '4px',
                marginBottom: '1.5rem',
                fontSize: '0.85rem',
                color: '#666'
              }}>
                ⚠️ <strong>Demo Only:</strong> This demo encrypts card data in the browser for educational purposes.
                Production systems should use Stripe Elements or server-side processing.
              </div>

              <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
                <button
                  type="button"
                  onClick={() => navigate('/')}
                  style={{
                    flex: 1,
                    backgroundColor: '#95a5a6',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '1rem',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    fontSize: '1rem'
                  }}
                >
                  Back to Menu
                </button>
                <button
                  type="submit"
                  disabled={isProcessing}
                  style={{
                    flex: 1,
                    backgroundColor: isProcessing ? '#95a5a6' : '#27ae60',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '1rem',
                    cursor: isProcessing ? 'not-allowed' : 'pointer',
                    fontWeight: 'bold',
                    fontSize: '1rem'
                  }}
                >
                  {isProcessing ? 'Processing...' : `Pay $${total.toFixed(2)}`}
                </button>
              </div>
            </form>
          </>
        )}
      </main>

      <Footer />
    </div>
  );
}

export default CheckoutPage;
