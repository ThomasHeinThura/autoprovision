import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build writes into app/dist/, which is committed. The jump host therefore
// needs neither Node nor npm registry access — a hard requirement in an
// air-gapped data centre.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../app/dist',
    emptyOutDir: true,
    // One vendor chunk keeps the committed diff small and predictable: an app
    // change does not rewrite the React bundle's hash.
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          markdown: ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:3000' },
  },
})
