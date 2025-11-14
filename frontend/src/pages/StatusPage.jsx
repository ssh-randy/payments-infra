import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import Header from '../components/Header';
import Footer from '../components/Footer';
import LoadingSpinner from '../components/LoadingSpinner';
import { pollPaymentStatus, getStripeDashboardLink } from '../services/api';

/**
 * StatusPage - Payment status polling page
 * Implements authorization polling and status display (i-5xjm)
 */
function StatusPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { clearCart } = useCart();
  const { authRequestId, totalCents } = location.state || {};

  const [status, setStatus] = React.useState('PROCESSING');
  const [statusData, setStatusData] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    if (!authRequestId) {
      navigate('/');
      return;
    }

    // Start polling for payment status
    console.log('[StatusPage] Starting status polling for:', authRequestId);

    const pollStatus = async () => {
      try {
        const result = await pollPaymentStatus(authRequestId);
        console.log('[StatusPage] Polling complete:', result);
        setStatus(result.status);
        setStatusData(result);

        // Clear cart on successful payment
        if (result.status === 'AUTHORIZED') {
          clearCart();
        }
      } catch (err) {
        console.error('[StatusPage] Polling error:', err);
        setError(err.message || 'Failed to retrieve payment status');
        setStatus('FAILED');
      }
    };

    pollStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequestId, navigate]);

  const formatCurrency = (cents) => {
    return `$${(cents / 100).toFixed(2)}`;
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  // Render processing state
  if (status === 'PROCESSING' || status === 'PENDING') {
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
          <LoadingSpinner message="Processing your payment..." />
          {authRequestId && (
            <div style={{ marginTop: '2rem', color: '#666', fontSize: '0.9rem' }}>
              <p>Authorization Request ID:</p>
              <p style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{authRequestId}</p>
              {totalCents && (
                <p style={{ marginTop: '1rem', fontSize: '1.1rem', fontWeight: 'bold' }}>
                  Order Total: {formatCurrency(totalCents)}
                </p>
              )}
            </div>
          )}
        </main>
        <Footer />
      </div>
    );
  }

  // Render authorized (success) state
  if (status === 'AUTHORIZED') {
    const stripeDashboardLink = statusData?.result?.processor_auth_id
      ? getStripeDashboardLink(statusData.result.processor_auth_id)
      : null;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Header />
        <main style={{
          flex: 1,
          maxWidth: '700px',
          width: '100%',
          margin: '0 auto',
          padding: '2rem'
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '2rem',
            borderRadius: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            textAlign: 'center'
          }}>
            <div style={{ fontSize: '4rem', color: '#27ae60', marginBottom: '1rem' }}>
              ✓
            </div>
            <h2 style={{ color: '#27ae60', marginBottom: '2rem' }}>
              Payment Successful!
            </h2>

            <div style={{ textAlign: 'left', marginBottom: '2rem' }}>
              <h3 style={{ borderBottom: '2px solid #eee', paddingBottom: '0.5rem' }}>
                Transaction Details
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: '0.75rem', padding: '1rem 0' }}>
                <strong>Auth Request ID:</strong>
                <span style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>{statusData.auth_request_id}</span>

                <strong>Status:</strong>
                <span style={{ color: '#27ae60', fontWeight: 'bold' }}>AUTHORIZED</span>

                {statusData.result?.processor_name && (
                  <>
                    <strong>Processor:</strong>
                    <span>{statusData.result.processor_name}</span>
                  </>
                )}

                {statusData.result?.processor_auth_code && (
                  <>
                    <strong>Auth Code:</strong>
                    <span style={{ fontFamily: 'monospace' }}>{statusData.result.processor_auth_code}</span>
                  </>
                )}

                {statusData.result?.processor_auth_id && (
                  <>
                    <strong>Processor ID:</strong>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>{statusData.result.processor_auth_id}</span>
                  </>
                )}

                {statusData.updated_at && (
                  <>
                    <strong>Timestamp:</strong>
                    <span>{formatTimestamp(statusData.updated_at)}</span>
                  </>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
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
                Place Another Order
              </button>

              {stripeDashboardLink && (
                <a
                  href={stripeDashboardLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    backgroundColor: '#6772e5',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '1rem 2rem',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    fontSize: '1rem',
                    textDecoration: 'none',
                    display: 'inline-block'
                  }}
                >
                  View on Stripe Dashboard →
                </a>
              )}
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  // Render denied state
  if (status === 'DENIED') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Header />
        <main style={{
          flex: 1,
          maxWidth: '600px',
          width: '100%',
          margin: '0 auto',
          padding: '2rem'
        }}>
          <div style={{
            backgroundColor: 'white',
            padding: '2rem',
            borderRadius: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            textAlign: 'center'
          }}>
            <div style={{ fontSize: '4rem', color: '#e74c3c', marginBottom: '1rem' }}>
              ✗
            </div>
            <h2 style={{ color: '#e74c3c', marginBottom: '1rem' }}>
              Payment Declined
            </h2>

            <div style={{
              backgroundColor: '#f8d7da',
              color: '#721c24',
              padding: '1rem',
              borderRadius: '4px',
              marginBottom: '2rem',
              textAlign: 'left'
            }}>
              {statusData?.result?.decline_reason && (
                <p><strong>Reason:</strong> {statusData.result.decline_reason}</p>
              )}
              {statusData?.result?.processor_decline_code && (
                <p><strong>Decline Code:</strong> {statusData.result.processor_decline_code}</p>
              )}
              {totalCents && (
                <p><strong>Order Total:</strong> {formatCurrency(totalCents)}</p>
              )}
            </div>

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
              <button
                onClick={() => navigate('/checkout')}
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
                Try Again
              </button>
              <button
                onClick={() => navigate('/')}
                style={{
                  backgroundColor: '#95a5a6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '1rem 2rem',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  fontSize: '1rem'
                }}
              >
                Back to Menu
              </button>
            </div>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  // Render failed state
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />
      <main style={{
        flex: 1,
        maxWidth: '600px',
        width: '100%',
        margin: '0 auto',
        padding: '2rem'
      }}>
        <div style={{
          backgroundColor: 'white',
          padding: '2rem',
          borderRadius: '8px',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '4rem', color: '#e74c3c', marginBottom: '1rem' }}>
            ⚠️
          </div>
          <h2 style={{ color: '#e74c3c', marginBottom: '1rem' }}>
            Payment Failed
          </h2>

          <div style={{
            backgroundColor: '#f8d7da',
            color: '#721c24',
            padding: '1rem',
            borderRadius: '4px',
            marginBottom: '2rem'
          }}>
            <p>{error || statusData?.result?.error_message || 'An unexpected error occurred'}</p>
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
            <button
              onClick={() => navigate('/checkout')}
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
              Retry
            </button>
            <button
              onClick={() => navigate('/')}
              style={{
                backgroundColor: '#95a5a6',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                padding: '1rem 2rem',
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '1rem'
              }}
            >
              Back to Menu
            </button>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default StatusPage;
