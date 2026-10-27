import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import PriceChart from '../components/PriceChart'
import VolumeChart from '../components/VolumeChart'
import AnomalyList from '../components/AnomalyList'

const REFRESH_INTERVAL_MS = 15000

function formatAutomationTime(value) {
  if (!value) return 'not yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'not yet' : date.toLocaleTimeString()
}

export default function MonitoringPage() {
  const navigate = useNavigate()
  const { symbol: symbolParam } = useParams()
  const [selectedSymbol, setSelectedSymbol] = useState(symbolParam?.toUpperCase() || '')
  const [account, setAccount] = useState(() => {
    const stored = localStorage.getItem('userId')
    const storedName = localStorage.getItem('userName')
    return stored ? { name: storedName || 'Demo User', email: 'demo@example.com', user_id: parseInt(stored, 10) } : null
  })
  const [chartTab, setChartTab] = useState('price')
  const [timeframe, setTimeframe] = useState('day')
  const [prices, setPrices] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [thresholds, setThresholds] = useState(null)
  const [health, setHealth] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)
  const [dataError, setDataError] = useState(null)
  const [showUserMenu, setShowUserMenu] = useState(false)

  const loadSelectedStockDetail = useCallback(async () => {
    if (!selectedSymbol) return
    try {
      const [p, a] = await Promise.all([
        api.getStockPrices(selectedSymbol, timeframe, 300),
        api.getStockAnomalies(selectedSymbol, 100, timeframe),
      ])
      setPrices(p)
      setAnomalies(a)
      setDataError(null)
      api.getThresholds(selectedSymbol, timeframe).then(setThresholds).catch(() => setThresholds(null))
    } catch (err) {
      setPrices([])
      setAnomalies([])
      setThresholds(null)
      setDataError(`Could not load price history: ${err.message}`)
    }
  }, [selectedSymbol, timeframe])

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.getHealth())
    } catch {
      setHealth({ status: 'unreachable' })
    }
  }, [])

  useEffect(() => {
    setSelectedSymbol(symbolParam?.toUpperCase() || '')
    loadSelectedStockDetail()
    loadHealth()
  }, [symbolParam, loadSelectedStockDetail, loadHealth])

  useEffect(() => { loadSelectedStockDetail() }, [loadSelectedStockDetail])
  useEffect(() => { loadHealth() }, [loadHealth])

  // Real-time-ish polling refresh
  useEffect(() => {
    const interval = setInterval(() => {
      loadSelectedStockDetail()
      loadHealth()
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [loadSelectedStockDetail, loadHealth])

  const signOut = async () => {
    try { await api.logout() } catch { /* expired session */ }
    navigate('/', { replace: true })
  }

  const runPipelineDemo = async () => {
    if (!selectedSymbol) return
    setActionMessage('Running pipeline…')
    try {
      const result = await api.processPipeline(selectedSymbol, timeframe === 'minute' ? 'minute' : 'day')
      setActionMessage(
        result.error
          ? `Error: ${result.error}`
          : `Reprocessed stored ${result.symbol} bar from ${new Date(result.timestamp).toLocaleString()}: ` +
            `${result.anomalies_detected} anomaly(ies), ` +
            `${result.alert_notifications_created} alert notification(s).`
      )
      loadSelectedStockDetail()
    } catch (err) {
      setActionMessage(`Error: ${err.message}`)
    }
  }

  const runHistoricalAnalysis = async () => {
    if (!selectedSymbol) return
    setActionMessage('Running historical analysis…')
    try {
      const result = await api.runAnalysis(selectedSymbol)
      setActionMessage(
        result.error ? `Error: ${result.error}` : `Historical analysis run #${result.analysis_id} completed.`
      )
      loadSelectedStockDetail()
    } catch (err) {
      setActionMessage(`Error: ${err.message}`)
    }
  }

  const runAlertCheck = async () => {
    setActionMessage('Checking alerts…')
    try {
      const result = await api.checkAlerts()
      setActionMessage(`Checked ${result.alerts_checked} alert(s); ${result.notifications_created} new notification(s).`)
    } catch (err) {
      setActionMessage(`Error: ${err.message}`)
    }
  }

  return (
    <div className="monitoring-page">
      <nav className="top-tabs" role="tablist" aria-label="Main navigation">
        <div className="nav-left">
          <span className="app-title">Stock Anomaly Monitor</span>
        </div>
        <div className="nav-center">
          <button
            role="tab"
            aria-selected={chartTab === 'price'}
            className={chartTab === 'price' ? 'active' : ''}
            onClick={() => setChartTab('price')}
          >
            Price
          </button>
          <button
            role="tab"
            aria-selected={chartTab === 'volume'}
            className={chartTab === 'volume' ? 'active' : ''}
            onClick={() => setChartTab('volume')}
          >
            Volume
          </button>
          <button
            role="tab"
            aria-selected={chartTab === 'anomalies'}
            className={chartTab === 'anomalies' ? 'active' : ''}
            onClick={() => setChartTab('anomalies')}
          >
            Anomalies
          </button>
        </div>
        <div className="nav-right">
          <div className="user-menu">
            <button
              className="about-button"
              onClick={() => setShowUserMenu(!showUserMenu)}
              aria-expanded={showUserMenu}
              aria-haspopup="true"
              aria-label="User menu"
            >
              About me?
            </button>
            {showUserMenu && (
              <div className="user-dropdown" role="menu">
                <div className="dropdown-header">
                  <span className="dropdown-user-id">{account?.name || 'User'}</span>
                  <span className="dropdown-guest">Guest</span>
                </div>
                <hr className="dropdown-divider" />
                <button className="dropdown-item about-styles" role="menuitem" onClick={() => { setShowUserMenu(false); navigate('/styles') }}>
                  Styles
                </button>
                <button className="dropdown-item signout" role="menuitem" onClick={signOut}>
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      <main className="main-content monitoring-main">

        <div className="monitoring-header">
          <h2>{selectedSymbol} — {timeframe === 'day' ? 'Daily' : 'Intraday'}</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} style={{ padding: '6px 10px', fontSize: 13 }}>
              <option value="day">Daily</option>
              <option value="minute">Minute</option>
            </select>
            <button className="ghost" onClick={runHistoricalAnalysis} style={{ padding: '6px 10px', fontSize: 12 }}>Run analysis</button>
            <button className="ghost" onClick={runPipelineDemo} style={{ padding: '6px 10px', fontSize: 12 }}>Reprocess bar</button>
            <button className="ghost" onClick={runAlertCheck} style={{ padding: '6px 10px', fontSize: 12 }}>Check alerts</button>
          </div>
        </div>

        <div className="status-bar">
          <span className={`dot${health && health.status === 'healthy' ? '' : ' bad'}`} />
          API: {health ? health.status : 'checking…'} · dashboard refresh {REFRESH_INTERVAL_MS / 1000}s
          {health?.automation && <>
            {' · automatic detection '}{health.automation.owner ? 'active' : health.automation.stream}
            {' · feed '}{health.automation.stream}
            {' · last refresh '}{formatAutomationTime(health.automation.last_data_refresh)}
            {' · last analysis '}{formatAutomationTime(health.automation.last_analysis)}
            {' · last alert check '}{formatAutomationTime(health.automation.last_alert_check)}
            {health.automation.last_error && <span className="error-text">{' · '}{health.automation.last_error}</span>}
          </>}
        </div>

        <button className="go-back" onClick={() => navigate('/overview', { replace: true })}>
          ← Go Back
        </button>

        {actionMessage && <p className="muted" style={{ fontSize: 12, margin: '12px 0 0' }}>{actionMessage}</p>}
        {thresholds && <p className="muted" style={{ fontSize: 11, margin: '8px 0 0' }}>
          Limits: {thresholds.ready
            ? `Return ${(thresholds.price_return_lower * 100).toFixed(2)}%–${(thresholds.price_return_upper * 100).toFixed(2)}% | Vol ${thresholds.volume_ratio_lower.toFixed(2)}×–${thresholds.volume_ratio_upper.toFixed(2)}× (${thresholds.samples} bars)`
            : thresholds.message}
        </p>}

        {dataError && <p className="error-text" role="alert">{dataError}</p>}

        <div className="chart-panel" style={{ marginTop: 16, height: 420, overflow: 'auto' }}>
          {chartTab === 'price' && <PriceChart symbol={selectedSymbol} prices={prices} anomalies={anomalies} />}
          {chartTab === 'volume' && <VolumeChart symbol={selectedSymbol} prices={prices} />}
          {chartTab === 'anomalies' && <AnomalyList anomalies={anomalies} compact />}
        </div>

      </main>
    </div>
  )
}