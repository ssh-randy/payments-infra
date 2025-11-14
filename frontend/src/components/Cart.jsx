import React from 'react';
import { useCart } from '../context/CartContext';
import { formatCurrencyCents } from '../utils/formatters';

/**
 * Cart component - displays cart summary with localStorage persistence
 */
function Cart({ onCheckout }) {
  const { cartItems, removeFromCart, updateQuantity, clearCart, calculateTotals, getItemCount } = useCart();
  const { subtotal_cents, tax_cents, total_cents } = calculateTotals();

  const handleClearCart = () => {
    if (window.confirm('Clear all items from cart?')) {
      clearCart();
    }
  };

  return (
    <div style={{
      border: '1px solid #ddd',
      borderRadius: '8px',
      padding: '1.5rem',
      backgroundColor: 'white',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      position: 'sticky',
      top: '2rem'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: '#333' }}>Your Cart</h2>
        {cartItems.length > 0 && (
          <span style={{
            backgroundColor: '#3498db',
            color: 'white',
            borderRadius: '50%',
            width: '24px',
            height: '24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.8rem',
            fontWeight: 'bold'
          }}>
            {getItemCount()}
          </span>
        )}
      </div>

      {cartItems.length === 0 ? (
        <div>
          <p style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', margin: '2rem 0' }}>
            Your cart is empty
          </p>
          <p style={{ color: '#999', fontSize: '0.9rem', textAlign: 'center' }}>
            Add items from the menu to get started!
          </p>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: '1rem' }}>
            {cartItems.map((item) => (
              <div
                key={item.menu_item_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.75rem 0',
                  borderBottom: '1px solid #eee'
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: '500', color: '#333' }}>{item.name}</div>
                  <div style={{ color: '#666', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                    {formatCurrencyCents(item.unit_price_cents)} each
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', marginTop: '0.5rem', gap: '0.5rem' }}>
                    <button
                      onClick={() => updateQuantity(item.menu_item_id, item.quantity - 1)}
                      style={{
                        backgroundColor: '#ecf0f1',
                        border: 'none',
                        borderRadius: '3px',
                        padding: '0.25rem 0.5rem',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                        fontWeight: 'bold',
                        color: '#333'
                      }}
                    >
                      −
                    </button>
                    <span style={{ fontSize: '0.9rem', minWidth: '20px', textAlign: 'center', color: '#333' }}>
                      {item.quantity}
                    </span>
                    <button
                      onClick={() => updateQuantity(item.menu_item_id, item.quantity + 1)}
                      style={{
                        backgroundColor: '#ecf0f1',
                        border: 'none',
                        borderRadius: '3px',
                        padding: '0.25rem 0.5rem',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                        fontWeight: 'bold',
                        color: '#333'
                      }}
                    >
                      +
                    </button>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem' }}>
                  <span style={{ fontWeight: 'bold', color: '#333' }}>
                    {formatCurrencyCents(item.subtotal_cents)}
                  </span>
                  <button
                    onClick={() => removeFromCart(item.menu_item_id)}
                    style={{
                      backgroundColor: '#e74c3c',
                      color: 'white',
                      border: 'none',
                      borderRadius: '3px',
                      padding: '0.25rem 0.5rem',
                      cursor: 'pointer',
                      fontSize: '0.75rem'
                    }}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={handleClearCart}
            style={{
              width: '100%',
              backgroundColor: '#95a5a6',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              padding: '0.5rem',
              marginBottom: '1rem',
              cursor: 'pointer',
              fontSize: '0.85rem'
            }}
          >
            Clear Cart
          </button>

          <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '2px solid #ddd' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', color: '#333' }}>
              <span>Subtotal:</span>
              <span>{formatCurrencyCents(subtotal_cents)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', color: '#333' }}>
              <span>Tax (9%):</span>
              <span>{formatCurrencyCents(tax_cents)}</span>
            </div>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontWeight: 'bold',
              fontSize: '1.2rem',
              marginTop: '0.5rem',
              paddingTop: '0.5rem',
              borderTop: '1px solid #ddd',
              color: '#333'
            }}>
              <span>Total:</span>
              <span>{formatCurrencyCents(total_cents)}</span>
            </div>
          </div>

          <button
            onClick={onCheckout}
            disabled={cartItems.length === 0}
            style={{
              width: '100%',
              backgroundColor: cartItems.length === 0 ? '#95a5a6' : '#27ae60',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              padding: '1rem',
              marginTop: '1rem',
              cursor: cartItems.length === 0 ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              fontSize: '1rem'
            }}
          >
            Proceed to Checkout
          </button>
        </>
      )}
    </div>
  );
}

export default Cart;
