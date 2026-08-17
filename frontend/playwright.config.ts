import { defineConfig, devices } from '@playwright/test'

// Keep mocked browser proof isolated from user-owned local apps. Port 3100 is
// commonly occupied by the adjacent Paperclip workspace on this machine.
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3117)
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  // The mocked suites share one stateful Next server and exercise several
  // layout-heavy Knowledge workspaces. Run them serially in every environment
  // so local release proof matches CI and cannot starve observers or corrupt
  // teardown traces under high browser concurrency.
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run build && PORT=${port} npm run start`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'mocked-browser',
      testIgnore: [
        'e2e/native/**',
        'e2e/device/**',
        // Podcast Studio proof binds to the controlled native runtime on 65060.
        'e2e/podcast-intelligence-studio.spec.ts',
        // Documentation screenshot harness — asserts nothing, costs ~50 s, and is
        // only run on demand when the user guide is regenerated. See
        // docs/user-guide/README.md.
        'e2e/docs-capture.spec.ts',
      ],
      use: {
        ...devices['Desktop Chrome'],
        locale: 'en-US',
        colorScheme: 'dark',
        deviceScaleFactor: 1,
      },
      metadata: {
        proof_boundary: 'mocked-browser',
        ci_gate: 'required-linux',
      },
    },
    {
      name: 'native-runtime',
      testMatch: [
        'e2e/native/**/*.spec.ts',
        'e2e/research-core-lab.spec.ts',
        'e2e/podcast-intelligence-studio.spec.ts',
      ],
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
