import React from 'react';
import { formatCurrencyCents } from '../utils/formatters';

/**
 * MenuItem component - displays a single menu item
 */
function MenuItem({ item, onAddToCart }) {
  return (
    <div style={{
      border: '1px solid #ddd',
      borderRadius: '8px',
      padding: '1.25rem',
      marginBottom: '1rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      backgroundColor: 'white',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      transition: 'box-shadow 0.2s ease',
      ':hover': {
        boxShadow: '0 2px 6px rgba(0,0,0,0.15)'
      }
    }}>
      <div style={{ flex: 1, marginRight: '1rem' }}>
        <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem', color: '#2c3e50' }}>
          {item?.name || 'Menu Item'}
        </h3>
        <p style={{ margin: '0 0 0.75rem 0', color: '#666', fontSize: '0.9rem', lineHeight: '1.4' }}>
          {item?.description || 'Description'}
        </p>
        <p style={{ margin: '0', fontWeight: 'bold', color: '#27ae60', fontSize: '1.1rem' }}>
          {formatCurrencyCents(item?.price_cents || 0)}
        </p>
      </div>
      <button
        onClick={() => onAddToCart && onAddToCart(item)}
        style={{
          backgroundColor: '#3498db',
          color: 'white',
          border: 'none',
          borderRadius: '6px',
          padding: '0.75rem 1.25rem',
          cursor: 'pointer',
          fontWeight: 'bold',
          fontSize: '0.95rem',
          transition: 'background-color 0.2s ease',
          whiteSpace: 'nowrap'
        }}
        onMouseOver={(e) => e.target.style.backgroundColor = '#2980b9'}
        onMouseOut={(e) => e.target.style.backgroundColor = '#3498db'}
      >
        Add to Cart
      </button>
    </div>
  );
}

export default MenuItem;
