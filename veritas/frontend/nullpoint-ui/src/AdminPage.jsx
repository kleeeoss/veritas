import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';
const API_TOKEN = import.meta.env.VITE_VERITAS_BEARER_TOKEN || '';

function AdminPage() {
  const [reviews, setReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

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
    } catch (_err) {
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
      await fetch(`${API_BASE}/api/v1/admin/reviews/${reviewId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
        },
        body: JSON.stringify({ decision }),
      });
      // Remove the item from the list in the UI for instant feedback
      setReviews(currentReviews => currentReviews.filter(item => item.id !== reviewId));
    } catch (_err) {
      alert('Failed to process decision.');
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
              <img
                src={`data:image/jpeg;base64,${item.image_data}`}
                alt={item.filename}
                style={{ maxWidth: '400px', border: '1px solid #555' }}
              />
              <div className="actions" style={{ marginTop: '1rem' }}>
                <button onClick={() => handleDecision(item.id, 'approve')} style={{ marginRight: '1rem' }}>
                  Approve (Genuine)
                </button>
                <button onClick={() => handleDecision(item.id, 'reject')}>
                  Reject (Forged)
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default AdminPage;
