import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AdminReviewPage.css'; // We'll create this CSS file next

function AdminReviewPage() {
  const [reviews, setReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // useEffect runs once when the component is first loaded
  useEffect(() => {
    const fetchReviews = async () => {
      setIsLoading(true);
      try {
        const response = await axios.get('http://localhost:8002/admin/reviews');
        setReviews(response.data.reviews || []); // Assumes the API returns { reviews: [...] }
      } catch (err) {
        setError('Failed to fetch documents for review.');
        console.error("Fetch reviews error:", err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchReviews();
  }, []); // The empty array [] tells React to only run this effect once

  // This function is called when an admin clicks "Approve" or "Reject"
  const handleDecision = async (id, decision) => {
    try {
      await axios.post(`http://localhost:8002/admin/reviews/${id}`, { decision });
      // For a better user experience, remove the item from the list immediately
      setReviews(currentReviews => currentReviews.filter(review => review.id !== id));
    } catch (err) {
      alert(`Failed to submit decision for document ${id}.`);
      console.error("Submit decision error:", err);
    }
  };

  if (isLoading) return <div className="loading">Loading documents for review...</div>;
  if (error) return <div className="error-message">{error}</div>;

  return (
    <div className="admin-review-page">
      <h2>Documents Flagged for Manual Review</h2>
      {reviews.length === 0 ? (
        <p>No documents are currently awaiting review.</p>
      ) : (
        <div className="review-list">
          {reviews.map((review) => (
            <div key={review.id} className="review-item">
              <div className="review-info">
                <p><strong>Document ID:</strong> {review.id}</p>
                <p><strong>Forgery Score:</strong> {(review.forgery_score * 100).toFixed(2)}%</p>
              </div>
              <div className="review-actions">
                <button className="approve-btn" onClick={() => handleDecision(review.id, 'approve')}>
                  Approve (Genuine)
                </button>
                <button className="reject-btn" onClick={() => handleDecision(review.id, 'reject')}>
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

export default AdminReviewPage;