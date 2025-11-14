import React from 'react';

function Footer() {
  return (
    <footer style={{
      backgroundColor: '#34495e',
      color: 'white',
      padding: '2rem',
      marginTop: 'auto',
      textAlign: 'center'
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <p style={{ margin: '0.5rem 0', fontSize: '0.9rem' }}>
          Demo Restaurant - Payment Infrastructure Demo
        </p>
        <p style={{ margin: '0.5rem 0', fontSize: '0.8rem', opacity: 0.7 }}>
          Test Mode - Use test card numbers only
        </p>
        <p style={{ margin: '0.5rem 0', fontSize: '0.8rem', opacity: 0.7 }}>
          Test Cards: 4242 4242 4242 4242 (success) | 4000 0000 0000 0002 (declined)
        </p>
      </div>
    </footer>
  );
}

export default Footer;
