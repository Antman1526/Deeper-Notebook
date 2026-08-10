import { expect, test } from './fixtures/research-workbench'

/**
 * Run only against a build made with NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0.
 * This is the explicit presentation rollback proof; it never changes data.
 */
test('legacy shell remains available through the explicit Folio rollback flag', async ({ page, researchWorkbench }) => {
  test.skip(
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO !== '0',
    'The rollback proof requires a build created with NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0.',
  )
  void researchWorkbench
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  await page.goto('/notebooks')

  await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: 'Deeper Notebook' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Primary tools' })).toHaveCount(0)
  await expect(page.locator('main')).toHaveCount(1)
})
