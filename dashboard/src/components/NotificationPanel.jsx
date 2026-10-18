import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function NotificationPanel({ userId, notifications, onChanged }) {
  const [error, setError] = useState(null)

  useEffect(() => setError(null), [userId])
  const handleMarkRead = async (notificationId) => {
    try {
      await api.markNotificationRead(userId, notificationId)
      setError(null)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const unreadCount = notifications.filter((n) => n.status === 'unread').length

  return (
    <div className="card">
      <h2>Notifications {unreadCount > 0 && <span className="badge unread">{unreadCount} unread</span>}</h2>
      {error && <p className="error-text" role="alert">{error}</p>}
      {notifications.length === 0 && <p className="muted">No notifications yet.</p>}
      {notifications.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When</th><th>Source</th><th>Symbol</th><th>Message</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {notifications.map((n) => (
              <tr key={n.notification_id}>
                <td>{new Date(n.created_at).toLocaleString()}</td>
                <td>{n.source === 'anomaly' ? 'Anomaly' : 'Price alert'}</td>
                <td>{n.symbol || '—'}</td>
                <td>{n.message}</td>
                <td><span className={`badge ${n.status}`}>{n.status}</span></td>
                <td>
                  {n.status === 'unread' && (
                    <button className="ghost" onClick={() => handleMarkRead(n.notification_id)}>Mark read</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
