import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import pkg from './package.json'

// backend origin for the /api proxy — dev server AND preview (playwright
// e2e points BACKEND_ORIGIN at a scratch backend on another port)
const backendOrigin = process.env.BACKEND_ORIGIN ?? 'http://localhost:8000'

// single source of truth for the UI version is package.json; the same
// value is exposed by the backend at /api/v1/health (backend/app/__init__.py)
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': backendOrigin,
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': backendOrigin,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // split the framework/UI libraries out of the route chunks; antd is
        // by far the largest and rarely changes between deploys
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('rc-')) {
            return 'antd'
          }
          if (id.includes('dayjs')) return 'dayjs'
          return 'vendor'
        },
      },
    },
  },
})
