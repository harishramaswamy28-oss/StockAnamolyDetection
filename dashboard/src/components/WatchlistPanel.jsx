import React, { useEffect, useState, useRef } from 'react'
import { api } from '../api/client'

export default function WatchlistPanel({ userId, watchlists, stocks, summaries, alerts, onChanged, onOpenStock }) {
  const [newName, setNewName] = useState('')
  const [symbolBySelect, setSymbolBySelect] = useState({})
  const [error, setError] = useState(null)
  const [scrollPosition, setScrollPosition] = useState(0)
  const [expandedWatchlist, setExpandedWatchlist] = useState(null)
  const containerRef = useRef(null)

  useEffect(() => {
    setError(null)
    setSymbolBySelect({})
  }, [userId])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    try {
      await api.createWatchlist(userId, newName.trim())
      setNewName('')
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleAdd = async (watchlistNo) => {
    const symbol = symbolBySelect[watchlistNo]
    if (!symbol) return
    try {
      await api.addStockToWatchlist(userId, watchlistNo, symbol)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleRemove = async (watchlistNo, symbol) => {
    try {
      await api.removeStockFromWatchlist(userId, watchlistNo, symbol)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = async (watchlistNo) => {
    try {
      await api.deleteWatchlist(userId, watchlistNo)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const scrollLeft = () => {
    if (containerRef.current) {
      containerRef.current.scrollBy({ left: -320, behavior: 'smooth' })
    }
  }

  const scrollRight = () => {
    if (containerRef.current) {
      containerRef.current.scrollBy({ left: 320, behavior: 'smooth' })
    }
  }

  const handleScroll = () => {
    if (containerRef.current) {
      setScrollPosition(containerRef.current.scrollLeft)
    }
  }

  const canScrollLeft = scrollPosition > 0
  const canScrollRight = containerRef.current && containerRef.current.scrollLeft + containerRef.current.clientWidth < containerRef.current.scrollWidth - 10

  return (
    <div className="card">
      <h2>Watchlists</h2>
      <p className="muted">Your focused market monitor. Prices, anomaly totals, and active price alerts refresh automatically with the dashboard.</p>
      {error && <p className="error-text">{error}</p>}

      <form className="inline-form" onSubmit={handleCreate} style={{ marginBottom: 20 }}>
        <input
          placeholder="New watchlist name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit" className="primary">Create watchlist</button>
      </form>

      {watchlists.length === 0 && <p className="muted">No watchlists yet. Create one above.</p>}

      {watchlists.length > 0 && (
        <div className="watchlist-carousel-wrapper">
          <button
            className="carousel-arrow left"
            onClick={scrollLeft}
            disabled={!canScrollLeft}
            aria-label="Scroll watchlists left"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          <div
            className="watchlist-carousel"
            ref={containerRef}
            onScroll={handleScroll}
          >
            {watchlists.map((w) => {
              const isExpanded = expandedWatchlist === w.watchlist_no
              const handleTileClick = (e) => {
                if (e.target.closest('button, select, option')) return
                setExpandedWatchlist(prev => prev === w.watchlist_no ? null : w.watchlist_no)
              }
              return (
                <div
                  className={`watchlist-tile${isExpanded ? ' expanded' : ''}`}
                  key={w.watchlist_no}
                  onClick={handleTileClick}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="watchlist-tile-header">
                    <strong>{w.name}</strong>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="expand-indicator" style={{ 
                        transition: 'transform 0.2s', 
                        transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                        color: 'var(--muted)',
                        fontSize: '12px'
                      }}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </span>
                      <button className="watchlist-delete" onClick={(e) => { e.stopPropagation(); handleDelete(w.watchlist_no) }} aria-label="Delete watchlist">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <div className="watchlist-tile-chips">
                    {w.stocks.map((s) => (
                      <span className="chip" key={s.security_id}>
                        {s.symbol}
                        <button onClick={(e) => { e.stopPropagation(); handleRemove(w.watchlist_no, s.symbol) }}>×</button>
                      </span>
                    ))}
                    {w.stocks.length === 0 && <span className="muted chip-empty">No stocks</span>}
                  </div>

                  {isExpanded && (
                    <div className="watchlist-tile-expanded">
                      {w.stocks.length > 0 && (
                        <div className="watchlist-tile-table">
                          <table>
                            <thead>
                              <tr>
                                <th>Stock</th>
                                <th>Price</th>
                                <th>Updated</th>
                                <th>Anomalies</th>
                                <th>Alerts</th>
                                <th></th>
                              </tr>
                            </thead>
                            <tbody>
                              {w.stocks.map((stock) => {
                                const summary = summaries?.[stock.symbol]
                                const stockAlerts = (alerts || []).filter((alert) => alert.symbol === stock.symbol && alert.status === 'active')
                                return (
                                  <tr key={stock.security_id}>
                                    <td>
                                      <strong>{stock.symbol}</strong>
                                      <div className="muted watchlist-company">{stock.name}</div>
                                    </td>
                                    <td>{summary?.latest_price != null ? `$${Number(summary.latest_price).toFixed(2)}` : '—'}</td>
                                    <td>{summary?.latest_timestamp ? new Date(summary.latest_timestamp).toLocaleString() : 'No data'}</td>
                                    <td>{summary?.total_anomalies ?? '—'}</td>
                                    <td>{stockAlerts.length ? stockAlerts.map((alert) => `${alert.condition} $${Number(alert.target_price).toFixed(2)}`).join(', ') : 'None'}</td>
                                    <td><button className="ghost" onClick={(e) => { e.stopPropagation(); onOpenStock(stock.symbol) }}>Monitor</button></td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                      <div className="watchlist-tile-add">
                        <select
                          value={symbolBySelect[w.watchlist_no] || ''}
                          onChange={(e) => { e.stopPropagation(); setSymbolBySelect({ ...symbolBySelect, [w.watchlist_no]: e.target.value }) }}
                        >
                          <option value="">Add stock…</option>
                          {stocks.map((s) => (
                            <option key={s.security_id} value={s.symbol}>{s.symbol}</option>
                          ))}
                        </select>
                        <button className="ghost" onClick={(e) => { e.stopPropagation(); handleAdd(w.watchlist_no) }}>Add</button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <button
            className="carousel-arrow right"
            onClick={scrollRight}
            disabled={!canScrollRight}
            aria-label="Scroll watchlists right"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}