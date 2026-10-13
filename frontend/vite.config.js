import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev-server proxy: React talks ONLY to FastAPI (same-origin /api paths).
const target = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
      },
    },
  },
});
