import { useState } from 'react';
import './App.css'; // This file provides basic styling

function App() {
  // This state will hold the file that the user selects
  const [selectedFile, setSelectedFile] = useState(null);
  // This state will hold the JSON response from the backend
  const [apiResponse, setApiResponse] = useState(null);

  // This function handles the file selection
  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
    setApiResponse(null); // Clear previous response
  };

  // This function handles the form submission
  const handleUpload = async (event) => {
    event.preventDefault(); // Prevents the default form submission behavior

    if (!selectedFile) {
      alert('Please select a file first!');
      return;
    }

    // Create a FormData object to send the file
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      // This is where you call Krish's backend endpoint!
      const response = await fetch('http://localhost:8001/veritas/verify', {
        method: 'POST',
        body: formData,
      });

      // Check if the request was successful
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Get the JSON data from the response
      const result = await response.json();
      setApiResponse(result);
      console.log('API Response:', result);

    } catch (error) {
      console.error('There was an error uploading the file:', error);
      alert('Failed to upload file. Check the console for details.');
    }
  };

return (
    <div className="App">
      <h1>Veritas Certificate Verification</h1>
      <form onSubmit={handleUpload}>
        <input type="file" onChange={handleFileChange} />
        <button type="submit">Verify Certificate</button>
      </form>

      {/* Conditional rendering: Only show results if we have an API response */}
      {apiResponse && (
        <div className="results-container">
          <h2>Verification Results:</h2>

          {/* Display the forgery score */}
          <p><strong>Forgery Score:</strong> {apiResponse.forgery_score}</p>

          {/* New Placeholder for the Heatmap */}
          <div>
            <h3>Forgery Heatmap:</h3>
            <p>Heatmap image will be displayed here.</p>
          </div>

          {/* New Placeholder for the Flag Reason */}
          <div>
            <h3>Flag Reason:</h3>
            <p>Reason for flagging will be displayed here.</p>
          </div>

          {/* Raw JSON Response for debugging */}
          <hr /> {/* This adds a horizontal line for separation */}
          <h3>Raw JSON Response:</h3>
          <pre>{JSON.stringify(apiResponse, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export default App;