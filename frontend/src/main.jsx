import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// StrictMode removed to prevent double API calls in development
ReactDOM.createRoot(document.getElementById('root')).render(
  <App />
)
