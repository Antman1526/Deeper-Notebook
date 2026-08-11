import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

test('Settings shows bounded backup and read-only provenance receipts', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'archive-paper' })
  await page.route('**/api/runtime/snapshot', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'runtime-snapshot-v1',
        status: 'ready',
        reasons: [],
        readiness: { state: 'ready', database: 'online', migrations: 'applied' },
        startup: { state: 'ready', stages: [] },
        updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
        vault: { state: 'ready', ready: 2, degraded: 0, unavailable: 0 },
        knowledge: { state: 'ready', projected: 2, unchanged: 1, failed: 0 },
        backup: {
          state: 'ready',
          freshness: 'valid',
          integrity: 'unknown',
          file_count: 1,
          newest_age_seconds: 30,
          newest_size_bytes: 2048,
          newest_timestamp: '2026-08-11T00:00:00+00:00',
        },
        provenance: {
          state: 'ready',
          mount_count: 2,
          external_read_only_count: 2,
          source_fingerprint_state: 'available',
        },
      }),
    })
  })

  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/settings')

  const panel = page.getByRole('region', { name: 'Backup and provenance' })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('Valid backup receipt')
  await expect(panel).toContainText('2 KB')
  await expect(panel).toContainText('2 external read-only spaces')
  await expect(panel).toContainText('Source fingerprints recorded')
  await expect(panel.getByRole('button')).toHaveCount(0)
  await expect(panel.getByRole('link')).toHaveCount(0)
})
