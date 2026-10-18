import React from 'react'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

export default function VolumeChart({ symbol, prices }) {
  const labels = prices.map((p) => new Date(p.timestamp).toLocaleString())
  const volumes = prices.map((p) => p.volume)

  const data = {
    labels,
    datasets: [
      {
        label: `${symbol} volume`,
        data: volumes,
        backgroundColor: 'rgba(242,184,75,0.6)',
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#8a93a6' } } },
    scales: {
      x: { ticks: { color: '#8a93a6', maxTicksLimit: 8 }, grid: { display: false } },
      y: { ticks: { color: '#8a93a6' }, grid: { color: '#2a3448' } },
    },
  }

  return (
    <div className="chart-wrap">
      {prices.length > 0 ? <Bar data={data} options={options} /> : <p className="muted">No volume data yet.</p>}
    </div>
  )
}
