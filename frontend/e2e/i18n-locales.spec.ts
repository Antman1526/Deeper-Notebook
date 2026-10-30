import { expect, test, type Page } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — the whole-app i18n pass moved ~2,000 hard-coded English strings into the
// 14 locales. These checks cover what unit tests cannot see: the live shell in another
// language, the document language, and longer translations fitting their controls.

async function open(page: Page, language: string, route: string) {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
  await page.addInitScript((code) => localStorage.setItem('i18nextLng', code), language)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(route)
}

for (const [language, label] of [['de-DE', 'Fokusmodus aktivieren'], ['ja-JP', '集中モードを開始']] as const) {
  test(`the Focus control speaks ${language}`, async ({ page }) => {
    await open(page, language, '/notebooks')
    await expect(page.getByTestId('focus-mode-control')).toHaveAccessibleName(label)
  })
}

test('the document language follows the selected language', async ({ page }) => {
  await open(page, 'de-DE', '/notebooks')
  await expect(page.locator('html')).toHaveAttribute('lang', 'de-DE')
})

test('German Knowledge utilities fit their buttons', async ({ page }) => {
  await open(page, 'de-DE', '/knowledge')
  const rail = page.locator('nav').filter({ has: page.getByRole('tablist') }).first()
  await expect(rail.getByRole('tab', { name: 'Arbeitsbereiche' })).toBeVisible()

  const problems = await rail.evaluate((nav) => {
    const out: string[] = []
    const bounds = nav.getBoundingClientRect()
    const buttons = Array.from(nav.querySelectorAll('button'))
    for (const button of buttons) {
      const box = button.getBoundingClientRect()
      if (button.scrollWidth > button.clientWidth + 1) out.push(`overflows: ${button.textContent}`)
      if (box.right > bounds.right + 1) out.push(`outside the rail: ${button.textContent}`)
    }
    const tabs = Array.from(nav.querySelectorAll('[role="tab"]'))
    for (const tab of tabs) {
      const label = document.createRange()
      label.selectNodeContents(tab)
      const text = label.getBoundingClientRect()
      const box = tab.getBoundingClientRect()
      if (text.left < box.left - 1 || text.right > box.right + 1) out.push(`tab text spills: ${tab.textContent}`)
    }
    return out
  })
  expect(problems).toEqual([])
})

test('the browser tab title speaks the selected language, and follows navigation', async ({ page }) => {
  await open(page, 'de-DE', '/notebooks')
  await expect(page).toHaveTitle('Notizbücher · Deeper Notebook')
  await page.getByRole('navigation', { name: 'Hauptnavigation' }).getByRole('link', { name: 'Fragen und Suchen' }).click()
  await expect(page).toHaveTitle('Fragen und Suchen · Deeper Notebook')
})

// Each page shipped all 14 locales (a 2.8 MB chunk). Only English is bundled now;
// the active language loads on demand.
async function scriptBodies(page: Page, run: () => Promise<void>): Promise<string> {
  const bodies: Promise<string>[] = []
  page.on('response', (response) => {
    if (response.request().resourceType() === 'script') bodies.push(response.text().catch(() => ''))
  })
  await run()
  return (await Promise.all(bodies)).join('\n')
}

test('an English page does not download the other languages', async ({ page }) => {
  const scripts = await scriptBodies(page, async () => {
    await open(page, 'en-US', '/notebooks')
    await expect(page.getByTestId('focus-mode-control')).toHaveAccessibleName('Enter focus mode')
  })
  for (const foreign of ['Fokusmodus aktivieren', '集中モードを開始', 'Notizbücher']) {
    expect(scripts.includes(foreign), `downloaded "${foreign}"`).toBe(false)
  }
})

test('a German page loads German, and only German', async ({ page }) => {
  const scripts = await scriptBodies(page, async () => {
    await open(page, 'de-DE', '/notebooks')
    await expect(page.getByTestId('focus-mode-control')).toHaveAccessibleName('Fokusmodus aktivieren')
  })
  expect(scripts.includes('Fokusmodus aktivieren'), 'German strings downloaded').toBe(true)
  expect(scripts.includes('集中モードを開始'), 'Japanese strings downloaded').toBe(false)
})
