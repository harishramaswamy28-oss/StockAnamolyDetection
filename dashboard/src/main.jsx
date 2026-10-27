import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App.jsx'
import Login from './pages/Login.jsx'
import Styles from './pages/Styles.jsx'
import MonitoringPage from './pages/MonitoringPage.jsx'
import Home from './pages/Home.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './index.css'
import './wrapper-style.css'

const THEMES = [
  { id: 'dark', bg: '#0F1115', panel: '#161A20', 'panel-alt': '#1C2128', 'panel-bg': 'rgba(22, 26, 32, 0.55)', text: '#E5E7EB', muted: '#9CA3AF', border: 'rgba(156,163,175,0.08)', accent: '#4f8cff' },
  { id: 'light', bg: '#F3F4F6', panel: '#FFFFFF', 'panel-alt': '#F9FAFB', 'panel-bg': 'rgba(255, 255, 255, 0.5)', text: '#111827', muted: '#6B7280', border: 'rgba(0,0,0,0.08)', accent: '#2563eb' },
  { id: 'blue', bg: '#0B1026', panel: '#121A33', 'panel-alt': '#121A33', 'panel-bg': 'rgba(18, 26, 51, 0.5)', text: '#E0E7FF', muted: '#93C5FD', border: 'rgba(59,130,246,0.15)', accent: '#2563eb' },
  { id: 'red', bg: '#2A0A0A', panel: '#350F0F', 'panel-alt': '#350F0F', 'panel-bg': 'rgba(53, 10, 10, 0.5)', text: '#FEE2E2', muted: '#FCA5A5', border: 'rgba(220,38,38,0.15)', accent: '#dc2626' },
  { id: 'green', bg: '#0A2B1E', panel: '#0D3B27', 'panel-alt': '#0D3B27', 'panel-bg': 'rgba(13, 59, 39, 0.5)', text: '#D1FAE5', muted: '#6EE7B7', border: 'rgba(16,185,129,0.15)', accent: '#059669' },
  { id: 'amber', bg: '#2E220A', panel: '#3F2F0E', 'panel-alt': '#3F2F0E', 'panel-bg': 'rgba(63, 47, 14, 0.5)', text: '#FEF3C7', muted: '#FCD34D', border: 'rgba(217,119,6,0.15)', accent: '#D97706' },
]

function applyStoredTheme() {
  const root = document.documentElement
  const stored = localStorage.getItem('selectedTheme') || 'dark'
  const theme = THEMES.find((t) => t.id === stored) || THEMES[0]
  root.style.setProperty('--base-deep', theme.bg)
    root.style.setProperty('--bg', theme.bg)
  root.style.setProperty('--panel', theme.panel)
  root.style.setProperty('--panel-alt', theme['panel-alt'] || theme.panel)
  root.style.setProperty('--panel-bg', theme['panel-bg'] || 'rgba(22, 26, 32, 0.55)')
  root.style.setProperty('--text', theme.text)
  root.style.setProperty('--muted', theme.muted)
  root.style.setProperty('--border', theme.border)
  root.style.setProperty('--accent', theme.accent)
}

applyStoredTheme()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/styles" element={<Styles />} />
          <Route path="/monitoring/:symbol" element={<MonitoringPage />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>,
)