import React, { useState } from 'react';
import VerificationPage from './VerificationPage';
import AdminPage from './AdminPage';

function App() {
  const [activePage, setActivePage] = useState('verification');

  return (
    <div className="App-container">
      <nav style={{ padding: '1rem', backgroundColor: '#282c34', width: '100%' }}>
        <button
          type="button"
          onClick={() => setActivePage('verification')}
          style={{ color: 'white', marginRight: '20px', background: 'transparent', border: '1px solid #fff' }}
        >
          Verification
        </button>
        <button
          type="button"
          onClick={() => setActivePage('admin')}
          style={{ color: 'white', background: 'transparent', border: '1px solid #fff' }}
        >
          Admin Review
        </button>
      </nav>

      {activePage === 'admin' ? <AdminPage /> : <VerificationPage />}
    </div>
  );
}

export default App;
