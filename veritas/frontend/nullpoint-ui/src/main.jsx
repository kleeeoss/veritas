// In src/main.jsx

import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom'; // The Router is imported here
import App from './App.jsx';
import './App.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* This is the ONLY <BrowserRouter> in your app. */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);