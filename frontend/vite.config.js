import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.js',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
    },
    // Stub heavy viz libraries that don't work in jsdom
    alias: {
      'plotly.js': new URL('./src/__mocks__/plotly.js', import.meta.url).pathname,
      'cytoscape': new URL('./src/__mocks__/cytoscape.js', import.meta.url).pathname,
      'cytoscape-dagre': new URL('./src/__mocks__/cytoscape-dagre.js', import.meta.url).pathname,
    },
  },
})
