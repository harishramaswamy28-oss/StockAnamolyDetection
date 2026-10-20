import React from 'react'

export default function AnomalyList({ anomalies, compact = false }) {
  if (compact) {
    return (
      <div style={{ padding: 0 }}>
        {anomalies.length === 0 && <p className="muted" style={{ marginTop: 20 }}>No anomalies detected for this stock yet.</p>}
        {anomalies.length > 0 && (
          <div style={{ maxHeight: '100%', overflow: 'auto' }}>
            <table style={{ width: '100%' }}>
              <thead>
                <tr style={{ position: 'sticky', top: 0, background: 'var(--panel)', zIndex: 1 }}>
                  <th style={{ padding: '10px 12px' }}>Timestamp</th>
                  <th style={{ padding: '10px 12px' }}>Type</th>
                  <th style={{ padding: '10px 12px' }}>Score</th>
                  <th style={{ padding: '10px 12px' }}>Threshold</th>
                  <th style={{ padding: '10px 12px' }}>Analysis run</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((a) => (
                  <tr key={a.anomaly_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 12px', fontSize: 13 }}>{new Date(a.timestamp).toLocaleString()}</td>
                    <td style={{ padding: '8px 12px' }}><span className={`badge ${a.anomaly_type}`}>{a.anomaly_type}</span></td>
                    <td style={{ padding: '8px 12px', fontSize: 13 }}>{a.anomaly_score.toFixed(2)}</td>
                    <td style={{ padding: '8px 12px', fontSize: 13 }}>{a.threshold.toFixed(2)}</td>
                    <td style={{ padding: '8px 12px', fontSize: 13 }} className="muted">#{a.analysis_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="card">
      <h2>Recent Anomalies</h2>
      {anomalies.length === 0 && <p className="muted">No anomalies detected for this stock yet.</p>}
      {anomalies.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Type</th>
              <th>Score</th>
              <th>Threshold</th>
              <th>Analysis run</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map((a) => (
              <tr key={a.anomaly_id}>
                <td>{new Date(a.timestamp).toLocaleString()}</td>
                <td><span className={`badge ${a.anomaly_type}`}>{a.anomaly_type}</span></td>
                <td>{a.anomaly_score.toFixed(2)}</td>
                <td>{a.threshold.toFixed(2)}</td>
                <td className="muted">#{a.analysis_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
