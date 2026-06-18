import { defineConfig } from '@playwright/test'

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
  webServer: [
    { command: 'bash e2e/backend.sh', url: 'http://127.0.0.1:8000/health/', timeout: 120_000, reuseExistingServer: false },
    { command: 'npm run dev', url: 'http://localhost:3000', timeout: 60_000, reuseExistingServer: false },
  ],
})
