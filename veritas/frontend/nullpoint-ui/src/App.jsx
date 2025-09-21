// In src/App.jsx
import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import VerificationPage from './VerificationPage';
import AdminPage from './AdminPage';

function App() {
  return (
    // 👇 APPLY THE CENTERING CLASS HERE
    <div className="App-container">
      <nav style={{ padding: '1rem', backgroundColor: '#282c34', width: '100%' }}>
        <Link to="/" style={{ color: 'white', marginRight: '20px' }}>Verification</Link>
        <Link to="/admin" style={{ color: 'white' }}>Admin Review</Link>
      </nav>

      {/* The rest of your content will now be centered */}
      <Routes>
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/" element={<VerificationPage />} />
      </Routes>
    </div>
  );
}

export default App;