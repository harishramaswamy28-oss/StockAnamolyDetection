import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api/client'
import StockOverview from './components/StockOverview'
import PriceChart from './components/PriceChart'
import VolumeChart from './components/VolumeChart'
import AnomalyList from './components/AnomalyList'
import WatchlistPanel from './components/WatchlistPanel'
import AlertPanel from './components/AlertPanel'
import NotificationPanel from './components/NotificationPanel'
import PreferencesPanel from './components/PreferencesPanel'
import PersonalDataQuery from './components/PersonalDataQuery'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'watchlists', label: 'Watchlists' },
  { id: 'alerts', label: 'Price Alerts' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'preferences', label: 'Preferences' },
  { id: 'database', label: 'My Data Queries' },
]

const REFRESH_INTERVAL_MS = 15000

function formatAutomationTime(value) {
  if (!value) return 'not yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'not yet' : date.toLocaleTimeString()
}

export default function App() {
  const navigate = useNavigate()
  const [account, setAccount] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const userId = account?.user_id
  const [activeTab, setActiveTab] = useState('monitoring')
  const [showUserMenu, setShowUserMenu] = useState(false)

  useEffect(() => {
    let active = true
    api.getAccount().then((current) => {
      if (active) setAccount(current)
    }).catch(() => {
      if (active) navigate('/login', { replace: true })
    }).finally(() => {
      if (active) setAuthReady(true)
    })
    const requireSignIn = () => {
      setAccount(null)
      navigate('/login', { replace: true })
    }
    window.addEventListener('auth-required', requireSignIn)
    return () => {
      active = false
      window.removeEventListener('auth-required', requireSignIn)
    }
  }, [navigate])

  const [stocks, setStocks] = useState([])
  const [summaries, setSummaries] = useState({})
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  const [chartTab, setChartTab] = useState('price')
  const [timeframe, setTimeframe] = useState('day')
  const [prices, setPrices] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [thresholds, setThresholds] = useState(null)

  const [watchlists, setWatchlists] = useState([])
  const [alerts, setAlerts] = useState([])
  const [notifications, setNotifications] = useState([])

  const [health, setHealth] = useState(null)
  const [actionMessage, setActionMessage] = useState(null)
  const [dataError, setDataError] = useState(null)

  const loadStocks = useCallback(async () => {
    try {
      const list = await api.getStocks()
      setStocks(list)
      if (list.length === 0) setSelectedSymbol(null)
      else if (!list.some((stock) => stock.symbol === selectedSymbol)) setSelectedSymbol(list[0].symbol)
      const summaryEntries = await Promise.all(
        list.map(async (s) => {
          try {
            return [s.symbol, await api.getStockSummary(s.symbol)]
          } catch {
            return [s.symbol, null]
          }
        })
      )
      setSummaries(Object.fromEntries(summaryEntries))
      setDataError(null)
    } catch (err) {
      setStocks([])
      setSummaries({})
      setSelectedSymbol(null)
      setDataError(`Could not load stocks: ${err.message}`)
    }
  }, [selectedSymbol])

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
      // Threshold context was added after the core chart API. Older running
      // API servers should not hide otherwise valid price and anomaly data.
      api.getThresholds(selectedSymbol, timeframe).then(setThresholds).catch(() => setThresholds(null))
    } catch (err) {
      setPrices([])
      setAnomalies([])
      setThresholds(null)
      setDataError(`Could not load price history: ${err.message}`)
    }
  }, [selectedSymbol, timeframe])

  const loadUserData = useCallback(async () => {
    if (!userId) return
    try {
      const [w, a, n] = await Promise.all([
        api.getWatchlists(userId),
        api.getAlerts(userId),
        api.getNotifications(userId),
      ])
      setWatchlists(w);
      setAlerts(a);
      setNotifications(n)
      setDataError(null)
    } catch (err) {
      setWatchlists([])
      setAlerts([])
      setNotifications([])
      setDataError(`Could not load data for user ${userId}: ${err.message}`)
    }
  }, [userId])

  const signOut = async () => {
    try { await api.logout() } catch { /* An expired session is already signed out. */ }
    setAccount(null)
    navigate('/login', { replace: true })
  }

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.getHealth())
    } catch {
      setHealth({ status: 'unreachable' })
    }
  }, [])

  useEffect(() => { loadStocks() }, [loadStocks])
  useEffect(() => { loadSelectedStockDetail() }, [loadSelectedStockDetail])
  useEffect(() => { loadUserData() }, [loadUserData])
  useEffect(() => { loadHealth() }, [loadHealth])

  // Real-time-ish polling refresh
  useEffect(() => {
    const interval = setInterval(() => {
      loadStocks()
      loadSelectedStockDetail()
      loadUserData()
      loadHealth()
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [loadStocks, loadSelectedStockDetail, loadUserData, loadHealth])

  if (!authReady) return <main className="auth-loading">Checking your session…</main>
  if (!account) return null

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
      loadUserData()
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
      loadStocks()
    } catch (err) {
      setActionMessage(`Error: ${err.message}`)
    }
  }

  const runAlertCheck = async () => {
    setActionMessage('Checking alerts…')
    try {
      const result = await api.checkAlerts()
      setActionMessage(`Checked ${result.alerts_checked} alert(s); ${result.notifications_created} new notification(s).`)
      loadUserData()
    } catch (err) {
      setActionMessage(`Error: ${err.message}`)
    }
  }

  return (
    <div className="app-shell">
      <nav className="top-tabs" role="tablist" aria-label="Main navigation">
        <div className="nav-left">
          <span className="app-title">Stock Anomaly Monitor</span>
        </div>
        <div className="nav-center">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? 'active' : ''}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="nav-right">
          <button
            className="about-button"
            onClick={() => setShowUserMenu(!showUserMenu)}
          >
            About me?
          </button>
          {showUserMenu && (
            <div className="about-dropdown" role="menu">
              <div className="about-dropdown-header">
                <span className="about-user-id">{account.name}</span>
                <span className="about-guest">{account.email}</span>
              </div>
              <hr className="about-divider" />
              <button className="about-item about-styles" role="menuitem" onClick={() => { setShowUserMenu(false); navigate('/styles') }}>
                Styles
              </button>
              <button className="about-item about-signout" role="menuitem" onClick={signOut}>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </nav>

      <main className="main-content">

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
        {dataError && <p className="error-text" role="alert">{dataError}</p>}

{activeTab === 'overview' && (
          <div className="card">
            <h2>Stock Overview</h2>
            <div className="grid">
              {stocks.map((stock) => {
                const summary = summaries[stock.symbol]
                const hasAnomalies = summary && summary.total_anomalies > 0
                return (
                  <button
                    type="button"
                    aria-pressed={selectedSymbol === stock.symbol}
                    key={stock.security_id}
                    className={`stock-tile${selectedSymbol === stock.symbol ? ' selected' : ''}`}
                    onClick={() => { setSelectedSymbol(stock.symbol); setActiveTab('monitoring') }}
                  >
                    <div className="symbol">{stock.symbol}</div>
                    <div className="company">{stock.name}</div>
                    <div className="price">
                      {summary && summary.latest_price != null ? `$${summary.latest_price.toFixed(2)}` : '—'}
                    </div>
                    <div className="muted" style={{ fontSize: 11 }}>
                      {summary && summary.latest_timestamp
                        ? new Date(summary.latest_timestamp).toLocaleString()
                        : 'no data yet'}
                    </div>
                    {hasAnomalies && (
                      <span className="anomaly-badge">{summary.total_anomalies} anomalies</span>
                    )}
                  </button>
                )
              })}
              {stocks.length === 0 && <p className="muted">No securities found. Run metadata ingestion first.</p>}
            </div>
          </div>
        )}

        {activeTab === 'monitoring' && (
          <>
            {selectedSymbol && (
              <div className="card monitoring-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
                  <h2 style={{ margin: 0 }}>{selectedSymbol} — {timeframe === 'day' ? 'Daily' : 'Intraday'}</h2>
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

                <div className="chart-tabs" role="tablist" aria-label="Chart selection">
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

                {actionMessage && <p className="muted" style={{ fontSize: 12, margin: '12px 0 0' }}>{actionMessage}</p>}
                {thresholds && <p className="muted" style={{ fontSize: 11, margin: '8px 0 0' }}>
                  Limits: {thresholds.ready
                    ? `Return ${(thresholds.price_return_lower * 100).toFixed(2)}%–${(thresholds.price_return_upper * 100).toFixed(2)}% | Vol ${thresholds.volume_ratio_lower.toFixed(2)}×–${thresholds.volume_ratio_upper.toFixed(2)}× (${thresholds.samples} bars)`
                    : thresholds.message}
                </p>}

                <div className="chart-panel" style={{ marginTop: 16, height: 420, overflow: 'auto' }}>
                  {chartTab === 'price' && <PriceChart symbol={selectedSymbol} prices={prices} anomalies={anomalies} />}
                  {chartTab === 'volume' && <VolumeChart symbol={selectedSymbol} prices={prices} />}
                  {chartTab === 'anomalies' && <AnomalyList anomalies={anomalies} compact />}
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'watchlists' && (
          <WatchlistPanel
            userId={userId}
            watchlists={watchlists}
            stocks={stocks}
            summaries={summaries}
            alerts={alerts}
            onChanged={loadUserData}
            onOpenStock={(symbol) => { setSelectedSymbol(symbol); setActiveTab('monitoring') }}
          />
        )}

        {activeTab === 'alerts' && (
          <AlertPanel userId={userId} alerts={alerts} stocks={stocks} onChanged={loadUserData} />
        )}

        {activeTab === 'notifications' && (
          <NotificationPanel userId={userId} notifications={notifications} onChanged={loadUserData} />
        )}

        {activeTab === 'preferences' && <PreferencesPanel userId={userId} />}
        {activeTab === 'database' && (
          <PersonalDataQuery
            userId={userId}
            watchlists={watchlists}
            alerts={alerts}
            notifications={notifications}
            onChanged={loadUserData}
            onAccountUpdated={async () => setAccount(await api.getAccount())}
          />
        )}
      </main>
    </div>
  )
}
