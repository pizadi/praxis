import { defineConfig, devices } from '@playwright/test'

/**
 * E2E against a REAL (scratch) stack — never the live containers:
 * webServer[0]: uvicorn on 127.0.0.1:18001 with its OWN fresh SQLite db +
 *              uploads dir (boot does migrations + bootstrap admin/admin123)
 * webServer[1]: vite preview (built dist) on 127.0.0.1:18010 proxying /api —
 *              reproduces the compose nginx routing.
 * System chromium: this sandbox cannot download browsers (registry mirrors);
 * /usr/bin/chromium runs with --no-sandbox here.
 */

const BACKEND_PORT = 18001
const FRONT_PORT = 18010

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: 'http://localhost:18010', // vite preview binds localhost (IPv6)
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'rm -rf /tmp/opencode/e2e-uploads && mkdir -p /tmp/opencode/e2e-uploads && ' +
        'rm -f /tmp/opencode/e2e.db && ' +
        'cd ../backend && ../.venv/bin/python -m uvicorn app.main:app ' +
        `--port ${BACKEND_PORT}`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:////tmp/opencode/e2e.db',
        UPLOAD_DIR: '/tmp/opencode/e2e-uploads',
        SECRET_KEY: 'e2e-secret-key-not-production',
        CLINIC_ENV: 'test',
        APP_TIMEZONE: 'Asia/Tehran',
      },
    },
    {
      command: `npm run preview -- --port ${FRONT_PORT} --strictPort`,
      url: `http://localhost:${FRONT_PORT}/`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { BACKEND_ORIGIN: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          // the sandbox uses the system chromium (no browser downloads);
          // CI installs playwright's own chromium and points here
          executablePath: process.env.E2E_CHROMIUM_PATH || '/usr/bin/chromium',
          args: ['--no-sandbox'],
        },
      },
      testIgnore: /mobile\.spec\.ts$/,
    },
    {
      // 390×844 phone — runs ONLY the mobile smoke spec
      // (browserName pinned: device descriptors default to webkit)
      name: 'chromium-mobile',
      use: {
        ...devices['iPhone 13'],
        browserName: 'chromium',
        launchOptions: {
          executablePath: process.env.E2E_CHROMIUM_PATH || '/usr/bin/chromium',
          args: ['--no-sandbox'],
        },
      },
      testMatch: /mobile\.spec\.ts$/,
    },
  ],
})
