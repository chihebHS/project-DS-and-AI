import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Les appels /api sont redirigés vers le backend FastAPI (port 8002)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: { '/api': 'http://127.0.0.1:8002' },
  },
})
