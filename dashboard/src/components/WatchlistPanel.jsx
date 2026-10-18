import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function WatchlistPanel({ userId, watchlists, stocks, summaries, alerts, onChanged, onOpenStock }) {
  const [newName, setNewName] = useState('')
  const [symbolBySelect, setSymbolBySelect] = useState({})
  const [error, setError] = useState(null)

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

  return (
    <div className="card">
      <h2>Watchlists</h2>
      <p className="muted">Your focused market monitor. Prices, anomaly totals, and active price alerts refresh automatically with the dashboard.</p>
      {error && <p className="error-text">{error}</p>}

      <form className="inline-form" onSubmit={handleCreate}>
        <input
          placeholder="New watchlist name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit" className="primary">Create watchlist</button>
      </form>

      {watchlists.length === 0 && <p className="muted">No watchlists yet.</p>}

      {watchlists.map((w) => (
        <div className="watchlist-block" key={w.watchlist_no}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>{w.name}</strong>
            <button className="danger" onClick={() => handleDelete(w.watchlist_no)}>Delete watchlist</button>
          </div>
          <div style={{ marginTop: 8 }}>
            {w.stocks.map((s) => (
              <span className="chip" key={s.security_id}>
                {s.symbol}
                <button onClick={() => handleRemove(w.watchlist_no, s.symbol)}>×</button>
              </span>
            ))}
            {w.stocks.length === 0 && <span className="muted">No stocks in this watchlist.</span>}
          </div>
          {w.stocks.length > 0 && (
            <div className="watchlist-table-wrap">
              <table className="watchlist-table">
                <thead><tr><th>Stock</th><th>Latest price</th><th>Last update</th><th>Recorded anomalies</th><th>Active alerts</th><th></th></tr></thead>
                <tbody>{w.stocks.map((stock) => {
                  const summary = summaries?.[stock.symbol]
                  const stockAlerts = (alerts || []).filter((alert) => alert.symbol === stock.symbol && alert.status === 'active')
                  return (
                    <tr key={stock.security_id}>
                      <td><strong>{stock.symbol}</strong><div className="muted watchlist-company">{stock.name}</div></td>
                      <td>{summary?.latest_price != null ? `$${Number(summary.latest_price).toFixed(2)}` : '—'}</td>
                      <td>{summary?.latest_timestamp ? new Date(summary.latest_timestamp).toLocaleString() : 'No price data'}</td>
                      <td>{summary?.total_anomalies ?? '—'}</td>
                      <td>{stockAlerts.length ? stockAlerts.map((alert) => `${alert.condition} $${Number(alert.target_price).toFixed(2)}`).join(', ') : 'None'}</td>
                      <td><button className="ghost" onClick={() => onOpenStock(stock.symbol)}>Monitor</button></td>
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
          )}
          <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
            <select
              value={symbolBySelect[w.watchlist_no] || ''}
              onChange={(e) => setSymbolBySelect({ ...symbolBySelect, [w.watchlist_no]: e.target.value })}
            >
              <option value="">Add stock…</option>
              {stocks.map((s) => (
                <option key={s.security_id} value={s.symbol}>{s.symbol}</option>
              ))}
            </select>
            <button className="ghost" onClick={() => handleAdd(w.watchlist_no)}>Add</button>
          </div>
        </div>
      ))}
    </div>
  )
}
