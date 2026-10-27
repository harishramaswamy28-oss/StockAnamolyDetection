// In local development, use Vite's same-origin proxy (also works with an API
// tunnel and keeps SameSite=Lax cookies first-party). Set VITE_API_BASE_URL
// for a deployed frontend that talks to a separately hosted API.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('auth-required'))
    }
    const body = await response.text()
    let message = body
    try {
      const payload = JSON.parse(body)
      const detail = payload.detail
      message = payload.error || (Array.isArray(detail)
        ? detail.map((item) => item.msg).join('; ')
        : detail) || body
    } catch {
      // Keep the response text when the server did not return JSON.
    }
    throw new Error(message ? `API error ${response.status}: ${message}` : `API error ${response.status}`)
  }
  const data = await response.json()
  if (data && !Array.isArray(data) && data.error) {
    throw new Error(data.error)
  }
  return data
}

export const api = {
  getAccount: () => request('/auth/me'),
  registerAccount: (name, email, password) => request('/auth/register', {
    method: 'POST', body: JSON.stringify({ name, email, password }),
  }),
  login: (email, password) => request('/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password }),
  }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  getPersonalQuerySchema: () => request('/database/query/schema'),
  runPersonalQuery: (query) => request('/database/query/run', {
    method: 'POST', body: JSON.stringify(query),
  }),

  // Stocks
  getStocks: () => request('/stocks'),
  getStockPrices: (symbol, timeframe = 'day', limit = 500) =>
    request(`/stocks/${symbol}/prices?timeframe=${timeframe}&limit=${limit}`),
  getStockAnomalies: (symbol, limit = 200, timeframe) =>
    request(`/stocks/${encodeURIComponent(symbol)}/anomalies?limit=${limit}${timeframe ? `&timeframe=${encodeURIComponent(timeframe)}` : ''}`),
  getStockSummary: (symbol) => request(`/stocks/${symbol}/summary`),
  getThresholds: (symbol, timeframe = 'day') =>
    request(`/stocks/${encodeURIComponent(symbol)}/thresholds?timeframe=${encodeURIComponent(timeframe)}`),

  // Watchlists
  getWatchlists: (userId) => request(`/users/${userId}/watchlists`),
  createWatchlist: (userId, name) =>
    request(`/users/${userId}/watchlists`, { method: 'POST', body: JSON.stringify({ name }) }),
  addStockToWatchlist: (userId, watchlistNo, symbol) =>
    request(`/users/${userId}/watchlists/${watchlistNo}/stocks`, {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),
  removeStockFromWatchlist: (userId, watchlistNo, symbol) =>
    request(`/users/${userId}/watchlists/${watchlistNo}/stocks/${symbol}`, { method: 'DELETE' }),
  deleteWatchlist: (userId, watchlistNo) =>
    request(`/users/${userId}/watchlists/${watchlistNo}`, { method: 'DELETE' }),

  // Alerts
  getAlerts: (userId) => request(`/users/${userId}/alerts`),
  createAlert: (userId, symbol, condition, targetPrice) =>
    request(`/users/${userId}/alerts`, {
      method: 'POST',
      body: JSON.stringify({ symbol, condition, target_price: targetPrice }),
    }),
  deleteAlert: (userId, alertNo) =>
    request(`/users/${userId}/alerts/${alertNo}`, { method: 'DELETE' }),
  evaluateAlert: (userId, alertNo) => request(`/users/${userId}/alerts/${alertNo}/evaluate`),

  // Notifications
  getNotifications: (userId) => request(`/users/${userId}/notifications`),
  markNotificationRead: (userId, notificationId) =>
    request(`/users/${userId}/notifications/${notificationId}/read`, { method: 'PATCH' }),

  // Preferences
  getPreferences: (userId) => request(`/users/${userId}/preferences`),
  updatePreferences: (userId, prefs) =>
    request(`/users/${userId}/preferences`, { method: 'PUT', body: JSON.stringify(prefs) }),

  // Processing / pipeline
  checkAlerts: () => request('/alerts/check', { method: 'POST' }),
  runAnalysis: (symbol) => request(`/analysis/run/${symbol}`, { method: 'POST' }),
  runAnalysisAll: () => request('/analysis/run', { method: 'POST' }),
  processPipeline: (symbol, timeframe = 'minute') =>
    request(`/pipeline/process/${symbol}?timeframe=${timeframe}`, { method: 'POST' }),

  getHealth: () => request('/health'),

}
