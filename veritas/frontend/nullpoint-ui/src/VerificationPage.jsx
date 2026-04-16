import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';
const API_TOKEN = import.meta.env.VITE_VERITAS_BEARER_TOKEN || '';
const MAX_POLL_ATTEMPTS = 90;
const POLL_INTERVAL_MS = 1000;

const isValidBase64 = (value) => {
  if (!value || typeof value !== 'string') return false;
  if (!/^[A-Za-z0-9+/=]+$/.test(value)) return false;
  try {
    const padded = value + '='.repeat((4 - (value.length % 4)) % 4);
    atob(padded);
    return true;
  } catch {
    return false;
  }
};

function VerificationPage() {
  // State to hold the selected file and its preview URL
  const [selectedFile, setSelectedFile] = useState(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState('');

  // State for the backend API result, loading status, and errors
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [jobStatus, setJobStatus] = useState('');

  const safeHeatmap = analysisResult?.heatmap && isValidBase64(analysisResult.heatmap)
    ? analysisResult.heatmap
    : null;
  const safePreviewUrl = imagePreviewUrl && imagePreviewUrl.startsWith('blob:') ? imagePreviewUrl : '';

  // This function is triggered when a user selects a file
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      setImagePreviewUrl(URL.createObjectURL(file));
      // Reset previous results when a new file is selected
      setAnalysisResult(null);
      setError('');
      setIdempotencyKey(crypto.randomUUID());
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
      setJobStatus('Submitting async verification job...');
      const response = await fetch(`${API_BASE}/api/v1/veritas/verify-async`, {
        method: 'POST',
        headers: {
          ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
          'Idempotency-Key': idempotencyKey || crypto.randomUUID(),
        },
        body: formData,
      });

      if (!response.ok) throw new Error(`Server responded with ${response.status}.`);
      const job = await response.json();
      setJobStatus(`Job queued: ${job.job_id}`);

      let pollCount = 0;
      let done = false;
      while (!done && pollCount < MAX_POLL_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        pollCount += 1;
        const jobRes = await fetch(`${API_BASE}/api/v1/veritas/jobs/${job.job_id}`, {
          headers: {
            ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
          },
        });
        if (!jobRes.ok) throw new Error(`Job status failed with ${jobRes.status}`);
        const statusPayload = await jobRes.json();
        setJobStatus(`Job status: ${statusPayload.status}`);
        if (statusPayload.status === 'completed') {
          done = true;
          setAnalysisResult(statusPayload.result);
          setJobStatus('Completed');
        } else if (statusPayload.status === 'failed') {
          done = true;
          throw new Error(statusPayload.error || 'Async job failed.');
        }
      }
      if (!done) {
        throw new Error('Verification job timed out while polling.');
      }

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
        {!isLoading && jobStatus && <p>{jobStatus}</p>}
        {error && <p className="error-message">{error}</p>}

        {/* --- Results Section --- */}
        {/* This entire section only renders after a successful API call */}
        {analysisResult && (
          <div className="results-section">
            <h2>Analysis Result</h2>
            <p><strong>Forgery Score:</strong> {analysisResult.forgery_score.toFixed(4)}</p>
            <p><strong>Risk Level:</strong> {analysisResult.risk_level}</p>
            <p><strong>Model Version:</strong> {analysisResult.model_version}</p>
            {needsReview && <p className="review-status">Status: Needs Manual Review</p>}

            <div className="image-container" style={{ aspectRatio: '11/8.5' }}>
              <img src={safePreviewUrl} alt="Uploaded Certificate" className="base-image" />
              {safeHeatmap && (
                <img
                  src={`data:image/jpeg;base64,${safeHeatmap}`}
                  alt="Forgery Heatmap"
                  className="heatmap-overlay"
                />
              )}
            </div>

            <p><strong>Extracted Text (OCR):</strong></p>
            <pre className="ocr-text-box">
              {JSON.stringify(analysisResult.ocr_text, null, 2)}
            </pre>
            <p><strong>Reason Codes:</strong> {analysisResult.reason_codes.join(', ')}</p>
            <h3>Detector Breakdown</h3>
            <ul>
              {analysisResult.detectors.map((detector) => (
                <li key={detector.detector}>
                  <strong>{detector.detector}</strong> ({detector.version}) — score: {detector.forgery_score.toFixed(3)}
                </li>
              ))}
            </ul>

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
