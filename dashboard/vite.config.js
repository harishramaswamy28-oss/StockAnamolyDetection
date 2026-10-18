import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dashboard dev server. The API base URL is read from VITE_API_BASE_URL at
// build/dev time (see .env.example in this directory); it defaults to the
// local FastAPI dev server address.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
})
