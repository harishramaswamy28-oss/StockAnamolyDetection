import React, { useState, useEffect, useCallback } from 'react'
import { api } from './api/client'
import StockOverview from './components/StockOverview'
import PriceChart from './components/PriceChart'
import VolumeChart from './components/VolumeChart'
import AnomalyList from './components/AnomalyList'
import WatchlistPanel from './components/WatchlistPanel'
import AlertPanel from './components/AlertPanel'
import NotificationPanel from './components/NotificationPanel'
import PreferencesPanel from './components/PreferencesPanel'

const TABS = [
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'watchlists', label: 'Watchlists' },
  { id: 'alerts', label: 'Price Alerts' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'preferences', label: 'Preferences' },
]

// Real-time monitoring uses simple polling (not websockets): every
// REFRESH_INTERVAL_MS, the dashboard re-fetches stock summaries, the selected
// stock's prices/anomalies, and notifications. This keeps the frontend
// implementation simple while still reflecting new bars/anomalies/alerts
// produced by the real-time stream processor without a manual page reload.
const REFRESH_INTERVAL_MS = 15000

function formatAutomationTime(value) {
  if (!value) return 'not yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'not yet' : date.toLocaleTimeString()
}

export default function App() {
  const [userId, setUserId] = useState(1)
  const [activeTab, setActiveTab] = useState('monitoring')

  const [stocks, setStocks] = useState([])
  const [summaries, setSummaries] = useState({})
  const [selectedSymbol, setSelectedSymbol] = useState(null)
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
      <aside className="sidebar">
        <h1>Stock Anomaly Monitor</h1>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`nav-item${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ marginTop: 24, padding: '0 8px' }}>
          <label className="muted" style={{ fontSize: 12 }}>
            User ID
            <input
              type="number"
              min="1"
              value={userId}
              onChange={(e) => setUserId(parseInt(e.target.value, 10) || 1)}
              style={{ width: '100%', marginTop: 4 }}
            />
          </label>
        </div>
      </aside>

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

        {activeTab === 'monitoring' && (
          <>
            <StockOverview
              stocks={stocks}
              summaries={summaries}
              selectedSymbol={selectedSymbol}
              onSelect={setSelectedSymbol}
            />

            {selectedSymbol && (
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                  <h2>{selectedSymbol} — Price &amp; Volume</h2>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                      <option value="day">Daily (historical)</option>
                      <option value="minute">Minute (intraday)</option>
                    </select>
                    <button className="ghost" onClick={runHistoricalAnalysis}>Run analysis now</button>
                    <button className="ghost" onClick={runPipelineDemo}>Reprocess stored bar</button>
                    <button className="ghost" onClick={runAlertCheck}>Check alerts now</button>
                  </div>
                </div>
                <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  Automatic monitoring processes each incoming minute bar and checks price alerts every minute.
                  Analysis actions are optional manual reruns. Reprocess stored bar re-evaluates saved data; it does not fetch a fresh price.
                </p>
                {actionMessage && <p className="muted" style={{ fontSize: 12 }}>{actionMessage}</p>}
                {thresholds && <p className="muted" style={{ fontSize: 12 }}>
                  Adaptive limits (rolling Q1 − 1.5×IQR / Q3 + 1.5×IQR): {thresholds.ready
                    ? `${timeframe} return ${(thresholds.price_return_lower * 100).toFixed(2)}% to ${(thresholds.price_return_upper * 100).toFixed(2)}%; volume ratio ${thresholds.volume_ratio_lower.toFixed(2)}× to ${thresholds.volume_ratio_upper.toFixed(2)}× (${thresholds.samples} prior bars)`
                    : thresholds.message}
                </p>}
                <PriceChart symbol={selectedSymbol} prices={prices} anomalies={anomalies} />
                <h3 style={{ marginTop: 24 }}>Volume</h3>
                <VolumeChart symbol={selectedSymbol} prices={prices} />
              </div>
            )}

            {selectedSymbol && <AnomalyList anomalies={anomalies} />}
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
      </main>
    </div>
  )
}
