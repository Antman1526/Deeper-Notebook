import { defineConfig, devices } from '@playwright/test'

const port = 3100
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run dev -- --hostname 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'mocked-browser',
      testIgnore: ['e2e/native/**', 'e2e/device/**'],
      use: { ...devices['Desktop Chrome'] },
      metadata: {
        proof_boundary: 'mocked-browser',
        ci_gate: 'required-linux',
      },
    },
    {
      name: 'native-runtime',
      testMatch: 'e2e/native/**/*.spec.ts',
      use: { ...devices['Desktop Chrome'] },
      metadata: {
        proof_boundary: 'native-runtime',
        ci_gate: 'platform-native-only',
      },
    },
    {
      name: 'packaged-device',
      testMatch: 'e2e/device/**/*.spec.ts',
      use: { ...devices['Desktop Chrome'] },
      metadata: {
        proof_boundary: 'packaged-device',
        ci_gate: 'manual-device-required',
        manual_requirements: 'installed app launch, microphone, and real local models',
      },
    },
  ],
})
