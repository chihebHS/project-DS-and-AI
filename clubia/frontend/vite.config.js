import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Les appels /api sont redirigés vers le backend FastAPI (port 8001)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8001' },
  },
})
