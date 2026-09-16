import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api sang FastAPI để dev không phải bật CORS lẫn đổi base URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
