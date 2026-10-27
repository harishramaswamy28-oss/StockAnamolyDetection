import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="home-page">
      <nav className="home-top-nav">
        <div className="nav-brand">
          Stock Anomaly <span>Monitor</span>
        </div>
        <div className="nav-ctas">
          <button className="btn-outline" onClick={() => navigate('/login')}>
            Login
          </button>
          <button className="btn-primary" onClick={() => navigate('/login')}>
            Sign up
          </button>
        </div>
      </nav>

      <div className="hero">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          <span>Real-time anomaly detection</span>
        </div>
        <h1>
          Monitor stock&nbsp;<em>anomalies in real time</em>
        </h1>
        <p className="hero-sub">
          Establish normal statistical behaviour from historical data, detect
          unusual price and volume movements on intraday bars, and manage user
          price alerts — all through a fast REST API and React dashboard.
        </p>
        <div className="hero-ctas">
          <button className="btn-primary" onClick={() => navigate('/login')}>
            Get started
          </button>
        </div>
        <div className="hero-metrics">
          <div className="metric">
            <div className="metric-value">4 <span>markets</span></div>
            <div className="metric-label">Tracked symbols</div>
          </div>
          <div className="metric">
            <div className="metric-value">24/7 <span>monitoring</span></div>
            <div className="metric-label">Intraday surveillance</div>
          </div>
          <div className="metric">
            <div className="metric-value">AI <span>powered</span></div>
            <div className="metric-label">Adaptive Tukey fences</div>
          </div>
        </div>
      </div>
    </div>
  )
}