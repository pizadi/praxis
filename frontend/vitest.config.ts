import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// separate from vite.config.ts (build stays untouched); tests live next to
// the code under test as *.test.ts(x)
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify('test'),
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})
