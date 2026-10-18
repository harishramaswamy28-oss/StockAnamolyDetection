import React from 'react'

export default function StockOverview({ stocks, summaries, selectedSymbol, onSelect }) {
  return (
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
              onClick={() => onSelect(stock.symbol)}
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
  )
}
