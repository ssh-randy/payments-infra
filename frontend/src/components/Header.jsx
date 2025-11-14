import React from 'react';

function Header() {
  return (
    <header style={{
      backgroundColor: '#2c3e50',
      color: 'white',
      padding: '1.5rem 2rem',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
    }}>
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <h1 style={{ margin: 0, fontSize: '1.8rem' }}>Demo Restaurant</h1>
        <p style={{ margin: 0, fontSize: '0.9rem', opacity: 0.8 }}>Online Ordering Demo</p>
      </div>
    </header>
  );
}

export default Header;
