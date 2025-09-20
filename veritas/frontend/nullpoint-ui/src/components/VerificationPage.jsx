import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../App.css';
import Spinner from './Spinner';
import Notification from './Notification';

function VerificationPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notification, setNotification] = useState({ message: '', type: '' });
  const [certificateData, setCertificateData] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const IS_GENUINE_THRESHOLD = 0.5;

  // This effect will make the notification disappear after 4 seconds
  useEffect(() => {
    if (notification.message) {
      const timer = setTimeout(() => {
        setNotification({ message: '', type: '' });
      }, 4000);
      return () => clearTimeout(timer); // Cleanup the timer
    }
  }, [notification]);

  const showNotification = (message, type) => {
    setNotification({ message, type });
  };

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
    setAnalysisResult(null);
    setCertificateData(null);
    setIsModalOpen(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      showNotification('Please select a file first.', 'error');
      return;
    }
    const formData = new FormData();
    formData.append('file', selectedFile);
    setIsLoading(true);
    try {
      const response = await axios.post('http://localhost:8002/veritas/verify', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAnalysisResult(response.data);
      showNotification('Analysis successful!', 'success');
    } catch (err) {
      showNotification('Failed to analyze document. Please try again.', 'error');
      console.error("API Error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleIssueCertificate = async () => {
    if (!analysisResult || !analysisResult.ocr_text) {
      showNotification('Cannot issue certificate without valid data.', 'error');
      return;
    }
    setIsLoading(true);
    try {
      const payload = { ocr_data: analysisResult.ocr_text };
      const response = await axios.post('http://localhost:8002/veritas/issue-certificate', payload);
      setCertificateData(response.data);
      setIsModalOpen(true);
      showNotification('Certificate issued successfully!', 'success');
    } catch (err) {
      showNotification('Failed to issue certificate.', 'error');
      console.error("Certificate Issuance Error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <Notification message={notification.message} type={notification.type} />
      <div className="content">
        <div className="upload-section">
          <input type="file" onChange={handleFileChange} accept="image/png, image/jpeg, image/jpg" />
          <button onClick={handleUpload} disabled={isLoading || !selectedFile}>
            Analyze Document
            {isLoading && !isModalOpen && <Spinner />}
          </button>
        </div>

        {analysisResult && (
          <div className="results-section">
            <h2>Analysis Results</h2>
            <div className="results-grid">
              <div className="result-item">
                <h3>Forgery Score</h3>
                <p className={analysisResult.forgery_score >= IS_GENUINE_THRESHOLD ? 'forged' : 'genuine'}>
                  {(analysisResult.forgery_score * 100).toFixed(2)}%
                </p>
              </div>
              <div className="result-item ocr-text"><h3>Extracted Text</h3><pre>{analysisResult.ocr_text || 'N/A'}</pre></div>
              <div className="result-item heatmap">
                <h3>Forgery Heatmap</h3>
                {analysisResult.heatmap ? (<img src={`data:image/png;base64,${analysisResult.heatmap}`} alt="Forgery heatmap" />) : (<p>N/A</p>)}
              </div>
            </div>
            <div className="issue-certificate-section">
              <button
                onClick={handleIssueCertificate}
                disabled={isLoading || analysisResult.forgery_score >= IS_GENUINE_THRESHOLD}
                title={analysisResult.forgery_score >= IS_GENUINE_THRESHOLD ? 'Only genuine documents can be certified' : 'Issue a signed certificate'}
              >
                Issue Signed Certificate
                {isLoading && isModalOpen && <Spinner />}
              </button>
            </div>
          </div>
        )}
      </div>

      {isModalOpen && certificateData && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2>Signed Digital Certificate</h2>
            <div className="certificate-details">
              <h4>Original Data:</h4>
              <pre>{JSON.stringify(certificateData.original_data, null, 2)}</pre>
              <h4>Digital Signature (ECDSA):</h4>
              <p className="signature">{certificateData.signature}</p>
              <div className="qr-code">
                <h4>Verification QR Code:</h4>
                <img src={`data:image/png;base64,${certificateData.qr_code_image}`} alt="Verification QR Code" />
              </div>
            </div>
            <button onClick={() => setIsModalOpen(false)}>Close</button>
          </div>
        </div>
      )}
    </>
  );
}

export default VerificationPage;