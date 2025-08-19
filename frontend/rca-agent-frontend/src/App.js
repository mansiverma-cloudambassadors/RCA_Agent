// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ChatPage from './ChatPage';
import './index.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <Routes>
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/" element={<Navigate to="/chat/new" />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;