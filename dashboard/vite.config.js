import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin dev proxy keeps the browser session cookie first-party while
// letting a collaborator point Vite at an API tunnel via API_PROXY_TARGET.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.API_PROXY_TARGET || 'http://127.0.0.1:8000'
  const apiPaths = [
    '/auth', '/database', '/users', '/stocks', '/alerts', '/analysis',
    '/pipeline', '/health', '/automation',
  ]

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: Object.fromEntries(apiPaths.map((path) => [path, {
        target: apiTarget,
        changeOrigin: true,
      }])),
    },
  }
})
