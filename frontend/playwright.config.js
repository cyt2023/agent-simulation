import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'
import { selectBrowserChannel } from './playwright.browserChannel.js'

const browserChannel = selectBrowserChannel({ exists: existsSync })
const chromiumUse = {
  ...devices['Desktop Chrome'],
  ...(browserChannel ? { channel: browserChannel } : {}),
}

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    { name: 'chromium', use: chromiumUse },
  ],
})
