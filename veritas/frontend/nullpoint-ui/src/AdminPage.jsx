import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';
const API_TOKEN = import.meta.env.VITE_VERITAS_BEARER_TOKEN || '';

function AdminPage() {
  const [reviews, setReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [historyByReview, setHistoryByReview] = useState({});

  // Function to fetch the list of documents for review
  const fetchReviews = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/reviews`, {
        headers: {
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
      });
      if (!response.ok) {
        throw new Error('Failed to fetch reviews.');
      }
      const data = await response.json();
      setReviews(data);
    } catch {
      setError('Could not load review data.');
    } finally {
      setIsLoading(false);
    }
  };

  // useEffect hook to fetch data when the component loads
  useEffect(() => {
    fetchReviews();
  }, []);

  // Function to handle the "Approve" or "Reject" action
  const handleDecision = async (reviewId, decision) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/reviews/${reviewId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
        body: JSON.stringify({ decision, notes: 'Reviewed from admin queue UI' }),
      });
      if (!response.ok) throw new Error('Decision failed');
      // Remove the item from the list in the UI for instant feedback
      setReviews(currentReviews => currentReviews.filter(item => item.id !== reviewId));
    } catch {
      alert('Failed to process decision.');
    }
  };

  const handleStartReview = async (reviewId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/reviews/${reviewId}/start`, {
        method: 'POST',
        headers: {
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
      });
      if (!response.ok) throw new Error('Start review failed');
      setReviews((current) => current.map((item) => (item.id === reviewId ? { ...item, status: 'in_review' } : item)));
    } catch {
      alert('Failed to mark review as in-progress.');
    }
  };

  const handleEscalate = async (reviewId) => {
    const reason = prompt('Escalation reason:');
    if (!reason) return;
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/reviews/${reviewId}/escalate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
        body: JSON.stringify({ reason }),
      });
      if (!response.ok) throw new Error('Escalation failed');
      setReviews((current) => current.map((item) => (item.id === reviewId ? { ...item, status: 'escalated', escalation_reason: reason } : item)));
    } catch {
      alert('Failed to escalate review.');
    }
  };

  const fetchHistory = async (reviewId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/admin/reviews/${reviewId}/history`, {
        headers: {
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
      });
      if (!response.ok) throw new Error('History fetch failed');
      const data = await response.json();
      setHistoryByReview((current) => ({ ...current, [reviewId]: data }));
    } catch {
      alert('Failed to fetch review history.');
    }
  };

  if (isLoading) return <p>Loading reviews...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;

  return (
    <div className="admin-page">
      <h1>Documents for Manual Review</h1>
      {reviews.length === 0 ? (
        <p>No documents are currently awaiting review.</p>
      ) : (
        <div className="review-list">
          {reviews.map((item) => (
            <div key={item.id} className="review-item" style={{ border: '1px solid #ccc', padding: '1rem', margin: '1rem' }}>
              <h3>{item.filename}</h3>
              <p>Forgery Score: {item.forgery_score.toFixed(4)}</p>
              <p>Risk Level: {item.risk_level}</p>
              <p>Status: {item.status}</p>
              {item.escalation_reason && <p>Escalation: {item.escalation_reason}</p>}
              <img
                src={`data:image/jpeg;base64,${item.image_data}`}
                alt={item.filename}
                style={{ maxWidth: '400px', border: '1px solid #555' }}
              />
              <div className="actions" style={{ marginTop: '1rem' }}>
                <button onClick={() => handleStartReview(item.id)} style={{ marginRight: '1rem' }}>
                  Start Review
                </button>
                <button onClick={() => handleDecision(item.id, 'approve')} style={{ marginRight: '1rem' }}>
                  Approve (Genuine)
                </button>
                <button onClick={() => handleDecision(item.id, 'reject')} style={{ marginRight: '1rem' }}>
                  Reject (Forged)
                </button>
                <button onClick={() => handleEscalate(item.id)} style={{ marginRight: '1rem' }}>
                  Escalate
                </button>
                <button onClick={() => fetchHistory(item.id)}>
                  View History
                </button>
              </div>
              {historyByReview[item.id] && (
                <div style={{ marginTop: '1rem', textAlign: 'left' }}>
                  <h4>Decision History</h4>
                  <ul>
                    {historyByReview[item.id].map((entry, index) => (
                      <li key={`${item.id}-history-${index}`}>
                        {entry.created_at} — {entry.action} by {entry.actor} {entry.notes ? `(${entry.notes})` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default AdminPage;
