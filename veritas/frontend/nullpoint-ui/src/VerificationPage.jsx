import React, { useState } from 'react';

function VerificationPage() {
  // State to hold the selected file and its preview URL
  const [selectedFile, setSelectedFile] = useState(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState('');

  // State for the backend API result, loading status, and errors
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // This function is triggered when a user selects a file
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      setImagePreviewUrl(URL.createObjectURL(file));
      // Reset previous results when a new file is selected
      setAnalysisResult(null);
      setError('');
    }
  };

  // This function sends the file to the backend for analysis
  const handleSubmit = async () => {
    if (!selectedFile) {
      setError('Please select a file first.');
      return;
    }

    setIsLoading(true);
    setAnalysisResult(null);
    setError('');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      // Replace with your actual backend endpoint
      const response = await fetch('http://localhost:8002/veritas/verify', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('Server responded with an error.');

      const data = await response.json();
      setAnalysisResult(data); // Store the full API response in state

    } catch (err) {
      setError('Failed to get analysis. Please try again.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  // --- DERIVED STATE ---
  // This logic determines if the "Issue Certificate" button should be active.
  // It's calculated directly from the 'analysisResult' state.
  const isGenuine = analysisResult && analysisResult.forgery_score < 0.4;
  const needsReview = analysisResult && analysisResult.needs_review;

  return (
    <div className="App">
      <header className="App-header">
        <h1>Veritas Document Verification</h1>

        {/* File Upload Section */}
        <div className="upload-section">
          <input type="file" onChange={handleFileChange} accept="image/png, image/jpeg" />
          <button onClick={handleSubmit} disabled={isLoading || !selectedFile}>
            {isLoading ? 'Analyzing...' : 'Verify Document'}
          </button>
        </div>

        {/* Display loading or error messages */}
        {isLoading && <p>Loading...</p>}
        {error && <p className="error-message">{error}</p>}

        {/* --- Results Section --- */}
        {/* This entire section only renders after a successful API call */}
        {analysisResult && (
          <div className="results-section">
            <h2>Analysis Result</h2>
            <p><strong>Forgery Score:</strong> {analysisResult.forgery_score.toFixed(4)}</p>
            {needsReview && <p className="review-status">Status: Needs Manual Review</p>}

            {/* FIX: The Layered Image Display */}
<div className="image-container" style={{ aspectRatio: '11/8.5' }}>
  <img src={imagePreviewUrl} alt="Uploaded Certificate" className="base-image" />
  {analysisResult && analysisResult.heatmap && (
    <img
      // This is the only line that changes: png -> jpeg
      src={`data:image/jpeg;base64,${analysisResult.heatmap}`}
      alt="Forgery Heatmap"
      className="heatmap-overlay"
    />
  )}
</div>

            <p><strong>Extracted Text (OCR):</strong></p>
            <pre className="ocr-text-box">
              {JSON.stringify(analysisResult.ocr_text, null, 2)}
            </pre>

            {/* FIX 2: The Conditionally Disabled Button */}
            <button className="issue-button" disabled={!isGenuine}>
              Issue Signed Certificate
            </button>
            {!isGenuine && (
              <p className="button-helper-text">
                <small>A certificate can only be issued for genuine documents.</small>
              </p>
            )}
          </div>
        )}
      </header>
    </div>
  );
}

export default VerificationPage;