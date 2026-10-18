import React, { useState, useEffect } from 'react'
import { api } from '../api/client'

export default function PreferencesPanel({ userId }) {
  const [prefs, setPrefs] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    setPrefs(null)
    setError(null)
    setSaved(false)
    api.getPreferences(userId)
      .then((p) => {
        if (cancelled) return
        setError(null)
        setPrefs(p)
      })
      .catch((err) => {
        if (cancelled) return
        setPrefs(null)
        setError(err.message)
      })
    return () => { cancelled = true }
  }, [userId])

  const handleSave = async (e) => {
    e.preventDefault()
    setSaved(false)
    try {
      await api.updatePreferences(userId, {
        price_alerts: prefs.price_alerts,
        anomaly_alerts: prefs.anomaly_alerts,
        notification_mode: prefs.notification_mode,
      })
      setError(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError(err.message)
    }
  }

  if (error) return <div className="card"><h2>Preferences</h2><p className="error-text">{error}</p></div>
  if (!prefs) return <div className="card"><h2>Preferences</h2><p className="muted">Loading…</p></div>

  return (
    <div className="card">
      <h2>Preferences</h2>
      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 360 }}>
        <label>
          <input
            type="checkbox"
            checked={prefs.price_alerts}
            onChange={(e) => setPrefs({ ...prefs, price_alerts: e.target.checked })}
          />{' '}
          Price alert notifications
        </label>
        <label>
          <input
            type="checkbox"
            checked={prefs.anomaly_alerts}
            onChange={(e) => setPrefs({ ...prefs, anomaly_alerts: e.target.checked })}
          />{' '}
          Anomaly notifications
        </label>
        <label>
          Notification mode:{' '}
          <select
            value={prefs.notification_mode}
            onChange={(e) => setPrefs({ ...prefs, notification_mode: e.target.value })}
          >
            <option value="in_app">in_app</option>
            <option value="email">email (config only — not actually sent)</option>
          </select>
        </label>
        <button className="primary" type="submit" style={{ width: 140 }}>Save</button>
        {saved && <span className="muted">Saved.</span>}
      </form>
    </div>
  )
}
