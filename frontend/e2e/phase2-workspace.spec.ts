import type { Page } from '@playwright/test'

import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'

// Phase 2 of the 2026-09-30 UI audit: the notebook workspace recomposition,
// proven against the production build.

const notebook = researchWorkbenchFixtures.notebook

// Same list mocks as phase0-defects.spec.ts: the generic fixture answers unmatched
// endpoints with `{}`, which crashes the notebook page into the Recovery Center.
async function mockNotebookPage(page: Page) {
  const json = (pattern: string, body: unknown) => page.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await json(`**/api/notebooks/${notebook.id}`, notebook)
  await json('**/api/notes**', [])
  await json('**/api/chat/sessions**', [])
  await json(`**/api/notebooks/${notebook.id}/suggested-questions**`, { questions: [] })
  await json(`**/api/studio/notebooks/${notebook.id}/artifacts**`, [])
  await json('**/api/models', [])
  await json('**/api/models/defaults', {})
  await json('**/api/mcp', [])
  await json('**/api/mcp/web-search', { enabled: false, provider: null, tool_name: 'web_search' })
}

test.beforeEach(async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
  await mockNotebookPage(page)
})

test.describe('2a — bounded frame', () => {
  for (const viewport of [
    { label: 'desktop', width: 1440, height: 900 },
    { label: 'phone', width: 390, height: 844 },
  ]) {
    test(`the page does not scroll itself on load (${viewport.label})`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/notebooks/${notebook.id}`)
      const heading = page.getByRole('heading', { level: 1, name: notebook.name })
      await expect(heading).toBeVisible()
      // Give the chat's scroll-to-bottom effect time to run (it used to scroll the
      // canvas ~936px on desktop and ~2,229px on a phone).
      await page.waitForTimeout(1500)

      const scroll = await page.evaluate(() => ({
        window: window.scrollY,
        canvas: document.querySelector('.dn-workspace-canvas')?.scrollTop ?? 0,
      }))
      expect(scroll).toEqual({ window: 0, canvas: 0 })
      const box = await heading.boundingBox()
      expect(box?.y ?? -1).toBeGreaterThanOrEqual(0)
      expect((box?.y ?? Infinity) + (box?.height ?? 0)).toBeLessThanOrEqual(viewport.height)
    })
  }

  test('the workspace fits the viewport and the chat composer is on screen', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    const main = page.getByRole('main', { name: notebook.name })
    await expect(main).toBeVisible()
    const mainBox = await main.boundingBox()
    expect((mainBox?.y ?? 0) + (mainBox?.height ?? Infinity)).toBeLessThanOrEqual(900)

    const composer = page.locator('main textarea[name="chat-message"]')
    await expect(composer).toBeInViewport()
  })

  test('the title bar holds the actions; Archive, Export and Delete are in the menu', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    await expect(page.getByTestId('executive-synthesis-button')).toBeVisible()
    await page.getByRole('button', { name: 'Notebook actions' }).click()
    await expect(page.getByRole('menuitem', { name: 'Archive' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /export/i })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Delete' })).toBeVisible()
  })

  test('Guided research and the Evidence Studio band live in the Studio column', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    const studio = page.getByRole('region', { name: 'Studio', exact: true })
    await expect(studio).toBeVisible()
    await expect(studio.getByRole('region', { name: 'Guided research workspace' })).toBeAttached()
    await expect(studio.getByRole('region', { name: 'Evidence Studio artifacts' })).toBeAttached()
  })
})

test.describe('2b — column cards', () => {
  for (const viewport of [
    { label: 'wide', width: 1440, height: 900 },
    { label: 'laptop', width: 1280, height: 800 },
    { label: 'compact', width: 1024, height: 768 },
  ]) {
    test(`column headers stay on one row and nothing clips (${viewport.label})`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/notebooks/${notebook.id}`)
      await expect(page.locator('main textarea[name="chat-message"]')).toBeVisible()

      const headers = await page.locator('[data-dn-column] > [data-slot="card-header"]').evaluateAll((elements) =>
        elements.filter((el) => (el as HTMLElement).offsetParent !== null).map((el) => ({
          height: el.getBoundingClientRect().height,
          overflow: el.scrollWidth - el.clientWidth,
        })),
      )
      expect(headers.length).toBeGreaterThanOrEqual(3)
      for (const header of headers) {
        // One row: 44px touch targets (the V2 floor) plus padding. A wrapped header is ~110px.
        expect(header.height).toBeLessThanOrEqual(80)
        expect(header.overflow).toBeLessThanOrEqual(1)
      }

      // v0.8.130 — the titles themselves read in full: header actions crowded "Sources" down
      // to "So…" at 1440 and "S" at 1024, and "Chat with Notebook" wrapped.
      const titles = await page.locator('[data-dn-column] > [data-slot="card-header"] [data-slot="card-title"]').evaluateAll((elements) =>
        elements.filter((el) => (el as HTMLElement).offsetParent !== null).map((el) => ({
          text: el.textContent?.trim(),
          truncated: el.scrollWidth - el.clientWidth,
          height: el.getBoundingClientRect().height,
        })),
      )
      expect(titles.length).toBeGreaterThanOrEqual(3)
      for (const title of titles) {
        expect(title, title.text).toEqual(expect.objectContaining({ truncated: 0 }))
        expect(title.height, title.text).toBeLessThanOrEqual(32)
      }

      // ...and so do the column action labels ("+ Add Source" read "A…" at 1280).
      const actions = await page.locator('[data-dn-column-actions] button').evaluateAll((elements) =>
        elements.filter((el) => (el as HTMLElement).offsetParent !== null).map((el) => ({
          name: el.getAttribute('aria-label') ?? el.textContent?.trim(),
          truncated: Math.max(0, ...Array.from(el.querySelectorAll('span')).map((span) => span.scrollWidth - span.clientWidth)),
        })),
      )
      expect(actions.length).toBeGreaterThanOrEqual(2)
      for (const action of actions) expect(action.truncated, action.name ?? '').toBe(0)
    })
  }

  test('columns are borderless surfaces on the tinted canvas', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    await expect(page.locator('main textarea[name="chat-message"]')).toBeVisible()

    const borders = await page.locator('[data-dn-column]').evaluateAll((elements) =>
      elements.map((el) => getComputedStyle(el).borderTopColor),
    )
    expect(borders.length).toBeGreaterThanOrEqual(4)
    for (const color of borders) expect(color).toMatch(/rgba\(0, 0, 0, 0\)|transparent/)
  })

  test('Studio leads with a two-column generator grid', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    const generate = page.getByRole('group', { name: 'Generate' })
    await expect(generate).toBeVisible()
    const columns = await generate.evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length)
    expect(columns).toBe(2)
  })
})

// v0.8.130 — Phase 2c: the chat column. A saved session with one finished answer.
const chatSession = {
  id: 'session-2c-001',
  notebook_id: notebook.id,
  title: 'Phase 2c chat',
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
  message_count: 2,
  model_override: null,
  disabled_mcp_servers: [],
}
const chatMessages = [
  { id: 'message-2c-human', type: 'human' as const, content: 'What does the source say?', timestamp: '2026-01-01T00:00:01Z' },
  { id: 'message-2c-ai', type: 'ai' as const, content: 'The source states a fixed research finding.', timestamp: '2026-01-01T00:00:02Z' },
]

async function mockChatHistory(page: Page, answer = chatMessages[1].content) {
  const json = (pattern: string, body: unknown) => page.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  // Registered after beforeEach, so these win over the empty-session mock.
  await json('**/api/chat/sessions**', [chatSession])
  const messages = [chatMessages[0], { ...chatMessages[1], content: answer }]
  await json(`**/api/chat/sessions/${chatSession.id}**`, { ...chatSession, messages })
}

test.describe('2c — chat column', () => {
  test('an empty chat shows no run panel', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    await expect(page.locator('main textarea[name="chat-message"]')).toBeVisible()
    await page.waitForTimeout(500)

    // The five-card "Run timeline · idle · no gate triggered" panel sat above every empty chat.
    await expect(page.getByRole('region', { name: 'Run timeline' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Run details' })).toHaveCount(0)
  })

  test('a finished run offers collapsed Run details under the answer', async ({ page }) => {
    await mockChatHistory(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    const answer = page.getByText(chatMessages[1].content)
    await expect(answer).toBeVisible()

    const details = page.getByRole('button', { name: 'Run details' })
    await expect(details).toHaveCount(1)
    await expect(details).toHaveAttribute('aria-expanded', 'false')
    const [answerBox, detailsBox] = await Promise.all([answer.boundingBox(), details.boundingBox()])
    expect(detailsBox!.y).toBeGreaterThan(answerBox!.y + answerBox!.height - 1)

    await details.click()
    await expect(details).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Model route')).toBeVisible()
    await expect(page.getByText('Context built')).toBeVisible()
  })

  test('opening Run details brings the facts into view', async ({ page }) => {
    // A long answer: the details open below the fold unless the chat scrolls to them.
    const longAnswer = Array.from({ length: 12 }, (_, i) => `Paragraph ${i + 1} of the grounded answer.`).join('\n\n')
    await mockChatHistory(page, longAnswer)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    await expect(page.getByText('Paragraph 12 of the grounded answer.')).toBeVisible()

    await page.getByRole('button', { name: 'Run details' }).click()
    await expect(page.getByText('Agent state')).toBeInViewport()
  })

  test('answers are flat and questions are tinted bubbles', async ({ page }) => {
    await mockChatHistory(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)
    await expect(page.getByText(chatMessages[1].content)).toBeVisible()

    const styles = await page.locator('[data-dn-message]').evaluateAll((elements) =>
      elements.map((el) => {
        const style = getComputedStyle(el)
        return {
          type: el.getAttribute('data-dn-message'),
          border: parseFloat(style.borderTopWidth),
          background: style.backgroundColor,
          image: style.backgroundImage,
        }
      }),
    )
    const ai = styles.find((s) => s.type === 'ai')
    const human = styles.find((s) => s.type === 'human')
    expect(ai).toEqual(expect.objectContaining({ border: 0, background: 'rgba(0, 0, 0, 0)', image: 'none' }))
    expect(human?.background).not.toBe('rgba(0, 0, 0, 0)')
    // A soft tint, not the old saturated gradient.
    expect(human?.image).toBe('none')

    // The evidence status is a quiet caption, not body-size text under every answer.
    const evidence = page.getByTestId('evidence-review')
    await expect(evidence).toBeVisible()
    expect(await evidence.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeLessThanOrEqual(12)
  })

  for (const viewport of [
    { label: 'wide', width: 1440, height: 900 },
    { label: 'compact', width: 1024, height: 768 },
  ]) {
    test(`the composer is a pill and the textarea owns its row (${viewport.label})`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/notebooks/${notebook.id}`)
      const textarea = page.locator('main textarea[name="chat-message"]')
      await expect(textarea).toBeVisible()

      const composer = page.locator('[data-dn-composer]')
      await expect(composer).toHaveCount(1)
      const [composerBox, textareaBox] = await Promise.all([composer.boundingBox(), textarea.boundingBox()])
      // At 1024 the mic and send buttons squeezed the textarea to ~95px ("Ask / anything / about").
      expect(textareaBox!.width).toBeGreaterThanOrEqual(composerBox!.width * 0.75)
      expect(await composer.evaluate((el) => parseFloat(getComputedStyle(el).borderTopLeftRadius))).toBeGreaterThanOrEqual(20)
      await expect(composer.getByRole('button', { name: 'Enter Debate mode' })).toBeVisible()
      await expect(composer.getByRole('button', { name: /send/i })).toBeVisible()
      // One row of controls: at 1024 the mic and send buttons wrapped below the model picker.
      const [modelBox, sendBox] = await Promise.all([
        composer.getByRole('button', { name: 'Default' }).boundingBox(),
        composer.getByRole('button', { name: /send/i }).boundingBox(),
      ])
      expect(Math.abs(modelBox!.y + modelBox!.height / 2 - (sendBox!.y + sendBox!.height / 2))).toBeLessThanOrEqual(4)
    })
  }

  test('Enter sends and Shift+Enter adds a line', async ({ page }) => {
    await mockChatHistory(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    const sends: string[] = []
    await page.route('**/api/chat/**', async (route) => {
      const request = route.request()
      if (request.method() === 'POST' && /\/api\/chat\/(stream|execute)/.test(request.url())) {
        sends.push(request.url())
        return route.abort()
      }
      return route.fallback()
    })
    await page.goto(`/notebooks/${notebook.id}`)
    await expect(page.getByText(chatMessages[1].content)).toBeVisible()

    const textarea = page.locator('main textarea[name="chat-message"]')
    await textarea.click()
    await page.keyboard.type('First line')
    await page.keyboard.press('Shift+Enter')
    await page.keyboard.type('second line')
    await expect(textarea).toHaveValue('First line\nsecond line')
    expect(sends).toHaveLength(0)

    await page.keyboard.press('Enter')
    await expect.poll(() => sends.length).toBe(1)
  })
})
