import React, { useState } from 'react';
import VerificationPage from './VerificationPage';
import AdminPage from './AdminPage';

const navStyle = { padding: '1rem', backgroundColor: '#282c34', width: '100%' };
const navButtonStyle = { color: 'white', background: 'transparent', border: '1px solid #fff' };

function App() {
  const [activePage, setActivePage] = useState('verification');

  return (
    <div className="App-container">
      <nav style={navStyle}>
        <button
          type="button"
          onClick={() => setActivePage('verification')}
          style={{ ...navButtonStyle, marginRight: '20px' }}
        >
          Verification
        </button>
        <button
          type="button"
          onClick={() => setActivePage('admin')}
          style={navButtonStyle}
        >
          Admin Review
        </button>
      </nav>

      {activePage === 'admin' ? <AdminPage /> : <VerificationPage />}
    </div>
  );
}

export default App;
