import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'register') await api.registerAccount(name, email, password)
      else await api.login(email, password)
      navigate('/overview', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-split">
        <div className="login-mural" aria-hidden="true">
          <div className="mural-layer mural-bg"></div>
          <div className="mural-layer mural-pattern"></div>
          <div className="mural-content">
            <div className="mural-title">Stock Anomaly Monitor</div>
            <div className="mural-subtitle">Real-time market intelligence at your fingertips</div>
            <div className="mural-stats">
              <div className="mural-stat">
                <span className="mural-stat-value">Live</span>
                <span className="mural-stat-label">market</span>
              </div>
              <div className="mural-stat">
                <span className="mural-stat-value">24/7</span>
                <span className="mural-stat-label">Monitoring</span>
              </div>
              <div className="mural-stat">
                <span className="mural-stat-value">AI</span>
                <span className="mural-stat-label">Powered</span>
              </div>
            </div>
            <div className="mural-illustration">
              <svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg" className="mural-chart">
                <defs>
                  <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="currentColor" stopOpacity="0.3"/>
                    <stop offset="100%" stopColor="currentColor" stopOpacity="0"/>
                  </linearGradient>
                </defs>
                <path d="M20 160 L60 120 L100 140 L140 90 L180 110 L220 70 L260 85 L280 60" 
                      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" opacity="0.8"/>
                <path d="M20 160 L60 120 L100 140 L140 90 L180 110 L220 70 L260 85 L280 60" 
                      stroke="url(#chartGradient)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="url(#chartGradient)"/>
                <circle cx="60" cy="120" r="5" fill="currentColor" opacity="0.8"/>
                <circle cx="140" cy="90" r="5" fill="var(--red)" opacity="0.9"/>
                <circle cx="220" cy="70" r="5" fill="var(--green)" opacity="0.9"/>
                <circle cx="280" cy="60" r="5" fill="var(--amber)" opacity="0.9"/>
              </svg>
            </div>
          </div>
          <div className="mural-decorations">
            <div className="deco deco-1"></div>
            <div className="deco deco-2"></div>
            <div className="deco deco-3"></div>
            <div className="deco deco-4"></div>
          </div>
        </div>
        <div className="login-panel">
          <div className="login-card">
            <div className="login-logo-image">
              <img src="/images/logo-1.png" alt="Stock Anomaly Monitor" onError={(e) => { e.target.style.display = 'none'; e.target.nextElementSibling.style.display = 'flex'; }} />
              <div className="login-logo-fallback" style={{display: 'none'}}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
            </div>
            <h1>{mode === 'login' ? 'Welcome Back' : 'Create your account'}</h1>
            <p className="login-subtitle">Your watchlists, alerts, and notifications are private to your account.</p>
            
            <form onSubmit={handleSubmit} className="login-form">
              {mode === 'register' && <div className="form-group">
                <label htmlFor="name">Name</label>
                <input id="name" type="text" required maxLength="200" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
              </div>}
              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  type="email"
                  required
                  maxLength="255"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="password">Password</label>
                <input id="password" type="password" required minLength={mode === 'register' ? 12 : 1} maxLength="128" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} />
                {mode === 'register' && <span className="muted">Use at least 12 characters.</span>}
              </div>
              
              {error && <p className="login-error" role="alert">{error}</p>}
              
              <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}</button>
            </form>
            
            <button type="button" className="login-mode-toggle" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
              {mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
