import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import VerificationPage from './components/VerificationPage';
import AdminReviewPage from './components/AdminReviewPage';
import './App.css';

function App() {
  return (
    <div className="App">
      <nav className="main-nav">
        <NavLink to="/">Verification</NavLink>
        <NavLink to="/admin">Admin Review</NavLink>
      </nav>

      <main>
        <Routes>
          <Route path="/" element={<VerificationPage />} />
          <Route path="/admin" element={<AdminReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;