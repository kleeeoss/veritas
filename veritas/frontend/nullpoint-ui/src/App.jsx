import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  // State variables to manage the UI and data
  const [selectedFile, setSelectedFile] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  /**
   * Handles the file input change event.
   * Updates the state with the selected file.
   */
  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
    setAnalysisResult(null); // Reset previous results on new file selection
    setError(''); // Clear any previous errors
  };

  /**
   * Handles the file upload and analysis request.
   * Sends the file to the backend API.
   */
  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file first.');
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    setIsLoading(true);
    setError('');

    try {
      const response = await axios.post('http://localhost:8002/veritas/verify', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setAnalysisResult(response.data);
    } catch (err) {
      setError('Failed to analyze the document. The backend might be down or an error occurred.');
      console.error("API Error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Veritas Document Forgery Detection</h1>
        <p>Upload a certificate image to verify its authenticity.</p>
      </header>

      <main className="content">
        <div className="upload-section">
          <input type="file" onChange={handleFileChange} accept="image/png, image/jpeg, image/jpg" />
          <button onClick={handleUpload} disabled={isLoading || !selectedFile}>
            {isLoading ? 'Analyzing...' : 'Analyze Document'}
          </button>
        </div>

        {error && <p className="error-message">{error}</p>}

        {analysisResult && (
          <div className="results-section">
            <h2>Analysis Results</h2>
            <div className="results-grid">
              <div className="result-item">
                <h3>Forgery Score</h3>
                <p className={analysisResult.forgery_score > 0.5 ? 'forged' : 'genuine'}>
                  {(analysisResult.forgery_score * 100).toFixed(2)}%
                </p>
                <span>(Higher score means more likely to be forged)</span>
              </div>

              <div className="result-item ocr-text">
                <h3>Extracted Text (OCR)</h3>
                <pre>{analysisResult.ocr_text || 'No text extracted.'}</pre>
              </div>

              <div className="result-item heatmap">
                <h3>Forgery Heatmap</h3>
                {analysisResult.heatmap ? (
                  <img
                    src={`data:image/png;base64,${analysisResult.heatmap}`}
                    alt="Forgery heatmap"
                  />
                ) : (
                  <p>Heatmap not available.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;