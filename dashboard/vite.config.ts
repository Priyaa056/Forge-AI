import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FORGE AI platform API (FastAPI, backend/main.py) runs on :8000.
// In development the dashboard calls relative /api paths and Vite proxies them there.
const PLATFORM_API = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: PLATFORM_API, changeOrigin: true },
      '/health': { target: PLATFORM_API, changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: PLATFORM_API, changeOrigin: true },
      '/health': { target: PLATFORM_API, changeOrigin: true },
    },
  },
});
