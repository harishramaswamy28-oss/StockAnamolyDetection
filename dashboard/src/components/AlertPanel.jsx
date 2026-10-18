import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function AlertPanel({ userId, alerts, stocks, onChanged }) {
  const [symbol, setSymbol] = useState('')
  const [condition, setCondition] = useState('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [error, setError] = useState(null)
  const [evaluated, setEvaluated] = useState({})

  useEffect(() => {
    setError(null)
    setEvaluated({})
    setSymbol('')
    setCondition('above')
    setTargetPrice('')
  }, [userId])

  const handleCreate = async (e) => {
    e.preventDefault()
    const numericTarget = Number(targetPrice)
    if (!symbol || !Number.isFinite(numericTarget) || numericTarget <= 0) {
      setError('Choose a stock and enter a target price greater than zero.')
      return
    }
    try {
      await api.createAlert(userId, symbol, condition, numericTarget)
      setError(null)
      setSymbol('')
      setTargetPrice('')
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = async (alertNo) => {
    try {
      await api.deleteAlert(userId, alertNo)
      setError(null)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleEvaluate = async (alertNo) => {
    try {
      const result = await api.evaluateAlert(userId, alertNo)
      setError(null)
      setEvaluated((current) => ({ ...current, [alertNo]: result }))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="card">
      <h2>Price Alerts</h2>
      <p className="muted" style={{ marginTop: -8 }}>
        Active alerts are checked automatically every minute and on each incoming price bar. When the latest price meets
        your above/below target condition, a notification is created in Notifications. Check now is optional.
      </p>
      {error && <p className="error-text">{error}</p>}

      <form className="inline-form" onSubmit={handleCreate}>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="">Symbol…</option>
          {stocks.map((s) => (
            <option key={s.security_id} value={s.symbol}>{s.symbol}</option>
          ))}
        </select>
        <select value={condition} onChange={(e) => setCondition(e.target.value)}>
          <option value="above">above</option>
          <option value="below">below</option>
        </select>
        <input
          type="number"
          min="0.01"
          step="0.01"
          placeholder="Target price"
          value={targetPrice}
          onChange={(e) => setTargetPrice(e.target.value)}
        />
        <button type="submit" className="primary">Create alert</button>
      </form>

      {alerts.length === 0 && <p className="muted">No alerts defined.</p>}
      {alerts.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Condition</th><th>Target</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.alert_no}>
                <td>{a.symbol}</td>
                <td>{a.condition}</td>
                <td>{a.target_price.toFixed(2)}</td>
                <td><span className={`badge ${a.status}`}>{a.status}</span></td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button className="ghost" onClick={() => handleEvaluate(a.alert_no)}>Check now</button>
                  <button className="danger" onClick={() => handleDelete(a.alert_no)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {Object.entries(evaluated).map(([alertNo, result]) => (
        <p key={alertNo} className="muted" style={{ fontSize: 12 }}>
          Alert #{alertNo}: {result.triggered ? 'TRIGGERED' : 'not triggered'}
          {result.current_price != null ? ` (current price ${result.current_price.toFixed(2)})` : ''}
          {result.timestamp ? ` at ${new Date(result.timestamp).toLocaleString()}` : ''}
          {result.triggered && !result.notification_created ? ' · unread notification already exists' : ''}
        </p>
      ))}
    </div>
  )
}
