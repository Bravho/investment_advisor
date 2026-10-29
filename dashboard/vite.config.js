import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3999,
    host: '0.0.0.0',
    proxy: {
      '/api/portfolio': {
        target: 'http://127.0.0.1:8996',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/portfolio/, ''),
      },
      '/api/advisor': {
        target: 'http://127.0.0.1:8998',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/advisor/, ''),
      },
      '/api/engine': {
        target: 'http://127.0.0.1:8997',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/engine/, ''),
      },
      '/api/council': {
        target: 'http://127.0.0.1:8993',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/council/, ''),
      },
    },
  },
  preview: { port: 3999, host: '0.0.0.0' },
  build: { outDir: 'dist' },
})
