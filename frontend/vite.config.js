import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend during development.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
