import React from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, TimeScale)

// Renders close price over time, overlaying anomaly markers so the user can
// see exactly which observation triggered a price anomaly.
export default function PriceChart({ symbol, prices, anomalies }) {
  const labels = prices.map((p) => new Date(p.timestamp).toLocaleString())
  const closeValues = prices.map((p) => p.close)

  const anomalyTimestamps = new Set(anomalies.map((a) => new Date(a.timestamp).getTime()))
  const anomalyPoints = prices.map((p) =>
    anomalyTimestamps.has(new Date(p.timestamp).getTime()) ? p.close : null
  )

  const data = {
    labels,
    datasets: [
      {
        label: `${symbol} close`,
        data: closeValues,
        borderColor: '#4f8cff',
        backgroundColor: 'rgba(79,140,255,0.08)',
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.15,
        fill: true,
      },
      {
        label: 'Anomaly',
        data: anomalyPoints,
        borderColor: '#ef5a6f',
        backgroundColor: '#ef5a6f',
        pointRadius: 5,
        pointStyle: 'triangle',
        showLine: false,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#8a93a6' } } },
    scales: {
      x: { ticks: { color: '#8a93a6', maxTicksLimit: 8 }, grid: { color: '#2a3448' } },
      y: { ticks: { color: '#8a93a6' }, grid: { color: '#2a3448' } },
    },
  }

  return (
    <div className="chart-wrap">
      {prices.length > 0 ? <Line data={data} options={options} /> : <p className="muted">No price data yet.</p>}
    </div>
  )
}
