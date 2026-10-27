import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from './api/client'
import WatchlistPanel from './components/WatchlistPanel'
import AlertPanel from './components/AlertPanel'
import NotificationPanel from './components/NotificationPanel'
import PreferencesPanel from './components/PreferencesPanel'
import PersonalDataQuery from './components/PersonalDataQuery'

const TABS = [
  { id: 'overview', label: 'Overview' },
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
  const location = useLocation()
  const [account, setAccount] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const userId = account?.user_id
  const [activeTab, setActiveTab] = useState('overview')
  const [showUserMenu, setShowUserMenu] = useState(false)

  // If we're on a monitoring route, redirect handling is in MonitoringPage
  useEffect(() => {
    if (location.pathname.startsWith('/monitoring/')) {
      // Don't render App tabs when on monitoring page
      return
    }
    setActiveTab('overview')
  }, [location.pathname])

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

  const [watchlists, setWatchlists] = useState([])
  const [alerts, setAlerts] = useState([])
  const [notifications, setNotifications] = useState([])

  const [health, setHealth] = useState(null)
  const [dataError, setDataError] = useState(null)

  const loadStocks = useCallback(async () => {
    try {
      const list = await api.getStocks()
      setStocks(list)
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
      setDataError(`Could not load stocks: ${err.message}`)
    }
  }, [])

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
    navigate('/', { replace: true })
  }

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.getHealth())
    } catch {
      setHealth({ status: 'unreachable' })
    }
  }, [])

  useEffect(() => { loadStocks() }, [loadStocks])
  useEffect(() => { loadUserData() }, [loadUserData])
  useEffect(() => { loadHealth() }, [loadHealth])

  // Real-time-ish polling refresh
  useEffect(() => {
    const interval = setInterval(() => {
      loadStocks()
      loadUserData()
      loadHealth()
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [loadStocks, loadUserData, loadHealth])

  if (!authReady) return <main className="auth-loading">Checking your session…</main>
  if (!account) return null

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
            <div className="user-dropdown" role="menu">
              <div className="dropdown-header">
                <span className="dropdown-user-id">{account.name}</span>
                <span className="dropdown-guest">Guest</span>
              </div>
              <hr className="dropdown-divider" />
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
                    aria-pressed={false}
                    key={stock.security_id}
                    className="stock-tile"
                    onClick={() => navigate(`/monitoring/${stock.symbol}`)}
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

        {activeTab === 'watchlists' && (
          <WatchlistPanel
            userId={userId}
            watchlists={watchlists}
            stocks={stocks}
            summaries={summaries}
            alerts={alerts}
            onChanged={loadUserData}
            onOpenStock={(symbol) => navigate(`/monitoring/${symbol}`)}
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