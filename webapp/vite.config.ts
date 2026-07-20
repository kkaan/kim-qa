import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: { plotly: ['plotly.js-basic-dist-min'] },
      },
    },
  },
});
