import React from 'react'

export default function AnomalyList({ anomalies }) {
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
