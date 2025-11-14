import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Header from '../components/Header';
import Footer from '../components/Footer';
import LoadingSpinner from '../components/LoadingSpinner';

/**
 * StatusPage - Payment status polling page
 * Placeholder for status polling implementation (i-5xjm)
 */
function StatusPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { paymentIntentId } = location.state || {};

  const [status, setStatus] = React.useState('processing');
  const [message, setMessage] = React.useState('Processing your payment...');

  React.useEffect(() => {
    if (!paymentIntentId) {
      navigate('/');
      return;
    }

    // Placeholder for status polling (to be implemented in i-5xjm)
    console.log('Polling payment status for:', paymentIntentId);

    // Simulate status polling
    const timer = setTimeout(() => {
      setStatus('succeeded');
      setMessage('Payment successful!');
    }, 3000);

    return () => clearTimeout(timer);
  }, [paymentIntentId, navigate]);

  const getStatusColor = () => {
    switch (status) {
      case 'succeeded':
        return '#27ae60';
      case 'failed':
        return '#e74c3c';
      case 'processing':
      default:
        return '#3498db';
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'succeeded':
        return '✓';
      case 'failed':
        return '✗';
      case 'processing':
      default:
        return '⟳';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />

      <main style={{
        flex: 1,
        maxWidth: '600px',
        width: '100%',
        margin: '0 auto',
        padding: '2rem',
        textAlign: 'center'
      }}>
        <h2>Payment Status</h2>

        {status === 'processing' ? (
          <LoadingSpinner message={message} />
        ) : (
          <div style={{
            backgroundColor: 'white',
            padding: '3rem',
            borderRadius: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            marginTop: '2rem'
          }}>
            <div style={{
              fontSize: '4rem',
              color: getStatusColor(),
              marginBottom: '1rem'
            }}>
              {getStatusIcon()}
            </div>
            <h3 style={{ color: getStatusColor(), marginBottom: '1rem' }}>
              {message}
            </h3>
            {paymentIntentId && (
              <p style={{ color: '#666', fontSize: '0.9rem', marginBottom: '2rem' }}>
                Payment ID: {paymentIntentId}
              </p>
            )}
            <button
              onClick={() => navigate('/')}
              style={{
                backgroundColor: '#3498db',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                padding: '1rem 2rem',
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '1rem'
              }}
            >
              {status === 'succeeded' ? 'Place Another Order' : 'Back to Menu'}
            </button>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}

export default StatusPage;
