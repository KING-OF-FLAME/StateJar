import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // scoped to /api/v1 so app routes like /api-keys aren't swallowed on hard refresh
      '/api/v1': 'http://localhost:8000',
    },
  },
})
