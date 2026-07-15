import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: 'http://localhost:3000',
    storageState: './e2e/.auth/state.json',
    trace: 'retain-on-failure',
  },
  // Nothing here has ever been tested at phone width. Phase 2 makes /supervisor
  // an installed PWA, so a layout regression has to fail CI before that lands.
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    { command: 'bash e2e/backend.sh', url: 'http://127.0.0.1:8000/health/', timeout: 120_000, reuseExistingServer: false },
    { command: 'npm run dev', url: 'http://localhost:3000', timeout: 60_000, reuseExistingServer: false },
  ],
})
