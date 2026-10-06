import { defineConfig, devices } from '@playwright/test'

// Keep mocked browser proof isolated from user-owned local apps. Port 3100 is
// commonly occupied by the adjacent Paperclip workspace on this machine.
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3117)
const baseURL = `http://127.0.0.1:${port}`
const ROLLBACK_VISUAL_SPECS = ['e2e/luminous-folio-visual.spec.ts', 'e2e/theme-gallery-visual.spec.ts']

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
    // v0.8.130 — PLAYWRIGHT_PREBUILT=1 skips the build: the rollback-visuals CI job builds
    // in its own step (with V2 off), so the build is not bound by this server timeout.
    // HOSTNAME pins the bind address to the baseURL host: Next reads it, and Docker (CI
    // container jobs included) sets it to the container id, so the server was unreachable.
    command: process.env.PLAYWRIGHT_PREBUILT === '1'
      ? `HOSTNAME=127.0.0.1 PORT=${port} npm run start`
      : `npm run build && HOSTNAME=127.0.0.1 PORT=${port} npm run start`,
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
        // Pre-V2 (rollback) presentation proofs: they need a build with
        // NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 and run in the rollback-visuals project.
        ...ROLLBACK_VISUAL_SPECS,
        // Documentation screenshot harness — asserts nothing, costs ~50 s, and is
        // only run on demand when the user guide is regenerated. Setting
        // DOCS_CAPTURE_DIR (which a capture run needs anyway) opts it back in, so
        // the exclusion never blocks the one command that wants it. See
        // docs/user-guide/README.md.
        ...(process.env.DOCS_CAPTURE_DIR ? [] : ['e2e/docs-capture.spec.ts']),
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
      // v0.8.130 — the Luminous (pre-V2) snapshot suites. V2 is a build-time flag and has
      // been the default since 2026-08-14, so these only render against a build made with
      // NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0: `npm run test:e2e:rollback-visuals`, and the
      // rollback-visuals CI job (Linux baselines come from the same Playwright image).
      name: 'rollback-visuals',
      testMatch: ROLLBACK_VISUAL_SPECS,
      use: {
        ...devices['Desktop Chrome'],
        locale: 'en-US',
        colorScheme: 'dark',
        deviceScaleFactor: 1,
      },
      metadata: {
        proof_boundary: 'mocked-browser-rollback',
        ci_gate: 'required-linux-v2-off',
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
