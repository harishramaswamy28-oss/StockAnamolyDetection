import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const THEMES = [
  { id: 'dark', label: 'Dark Mode', accent: '#4f8cff', bg: '#0F1115', panel: '#161A20', 'panel-alt': '#1C2128', 'panel-bg': 'rgba(22, 26, 32, 0.55)', text: '#E5E7EB', muted: '#9CA3AF', border: 'rgba(156,163,175,0.08)' },
  { id: 'light', label: 'Light Mode', accent: '#2563eb', bg: '#F3F4F6', panel: '#FFFFFF', 'panel-alt': '#F9FAFB', 'panel-bg': 'rgba(255, 255, 255, 0.5)', text: '#111827', muted: '#6B7280', border: 'rgba(0,0,0,0.08)' },
  { id: 'blue', label: 'Blue Mode', accent: '#2563eb', bg: '#0B1026', panel: '#121A33', 'panel-alt': '#121A33', 'panel-bg': 'rgba(18, 26, 51, 0.5)', text: '#E0E7FF', muted: '#93C5FD', border: 'rgba(59,130,246,0.15)' },
  { id: 'red', label: 'Red Mode', accent: '#dc2626', bg: '#2A0A0A', panel: '#350F0F', 'panel-alt': '#350F0F', 'panel-bg': 'rgba(53, 10, 10, 0.5)', text: '#FEE2E2', muted: '#FCA5A5', border: 'rgba(220,38,38,0.15)' },
  { id: 'green', label: 'Green Mode', accent: '#059669', bg: '#0A2B1E', panel: '#0D3B27', 'panel-alt': '#0D3B27', 'panel-bg': 'rgba(13, 59, 39, 0.5)', text: '#D1FAE5', muted: '#6EE7B7', border: 'rgba(16,185,129,0.15)' },
  { id: 'amber', label: 'Amber Mode', accent: '#D97706', bg: '#2E220A', panel: '#3F2F0E', 'panel-alt': '#3F2F0E', 'panel-bg': 'rgba(63, 47, 14, 0.5)', text: '#FEF3C7', muted: '#FCD34D', border: 'rgba(217,119,6,0.15)' },
]

export default function StylesPage() {
  const navigate = useNavigate()
  const [selectedTheme, setSelectedTheme] = useState(() => localStorage.getItem('selectedTheme') || 'dark')

  const applyTheme = (theme) => {
    const root = document.documentElement
    root.style.setProperty('--base-deep', theme.bg)
    root.style.setProperty('--bg', theme.bg)
    root.style.setProperty('--panel', theme.panel)
    root.style.setProperty('--panel-alt', theme['panel-alt'] || theme.panel)
    root.style.setProperty('--panel-bg', theme['panel-bg'] || 'rgba(22, 26, 32, 0.55)')
    root.style.setProperty('--text', theme.text)
    root.style.setProperty('--muted', theme.muted)
    root.style.setProperty('--border', theme.border)
    root.style.setProperty('--accent', theme.accent)
    localStorage.setItem('selectedTheme', theme.id)
    setSelectedTheme(theme.id)
  }

  useEffect(() => {
    applyTheme(THEMES.find((t) => t.id === selectedTheme) || THEMES[0])
  }, [selectedTheme])

  const goBack = () => navigate('/overview')

  return (
    <div className="styles-page">
      <div className="styles-header">
        <button className="styles-back" onClick={goBack}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back to Dashboard
        </button>
        <h1>Theme Styles</h1>
        <p className="styles-subtitle">Choose a color mode for the dashboard</p>
      </div>

      <div className="styles-grid">
        {THEMES.map((theme) => (
          <button
            key={theme.id}
            className={`styles-theme-card${selectedTheme === theme.id ? ' active' : ''}`}
            onClick={() => applyTheme(theme)}
          >
            <div className="styles-theme-preview">
              <div className="styles-theme-accent-bar" style={{ background: theme.accent }} />
              <div className="styles-theme-bg" style={{ background: theme.bg }} />
              <div className="styles-theme-panel" style={{ background: theme.panel }} />
            </div>
            <div className="styles-theme-info">
              <span className="styles-theme-name">{theme.label}</span>
              <span className="styles-theme-id">{theme.id}</span>
            </div>
            {selectedTheme === theme.id && (
              <svg className="styles-theme-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </button>
        ))}
      </div>

      <div className="styles-preview-note">
        <p>The theme applies instantly to all dashboard components — nav, cards, charts, watchlists, and buttons.</p>
      </div>
    </div>
  )
}