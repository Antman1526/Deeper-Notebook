import fs from 'node:fs'
import path from 'node:path'

import { chromium, type Browser } from '@playwright/test'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

// T0-10 — at phone width the Evidence Studio spread kept its two-column grid.
// The variant rule `[data-dn-folio-spread][data-dn-folio-variant='evidence-studio']`
// (specificity 0,2,0) beat the narrow-width single-column override, which only
// named `[data-dn-folio-spread]` (0,1,0). The 18rem second column left the source
// desk about 22px wide and the output-mode panel painted over it.

vi.setConfig({ testTimeout: 60_000, hookTimeout: 60_000 })

const folioCss = fs.readFileSync(path.resolve(__dirname, 'folio.css'), 'utf8')

const spread = (variant?: string) => `
  <!doctype html>
  <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        html, body { margin: 0; }
        :root { --dn-space-4: 1rem; --dn-space-6: 1.5rem; }
        ${folioCss}
      </style>
    </head>
    <body>
      <div data-dn-folio-spread ${variant ? `data-dn-folio-variant="${variant}"` : ''}>
        <section id="primary" data-dn-folio-primary>Source desk with enough text to need real width.</section>
        <section id="secondary" data-dn-folio-secondary>Output mode</section>
      </div>
    </body>
  </html>
`

let browser: Browser

beforeAll(async () => {
  browser = await chromium.launch({ headless: true })
})

afterAll(async () => {
  await browser?.close()
})

async function layout(html: string, width: number) {
  const context = await browser.newContext({ viewport: { width, height: 900 } })
  try {
    const tab = await context.newPage()
    await tab.setContent(html)
    return await tab.evaluate(() => {
      const box = (id: string) => {
        const rect = document.getElementById(id)!.getBoundingClientRect()
        return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right, width: rect.width }
      }
      return { primary: box('primary'), secondary: box('secondary') }
    })
  } finally {
    await context.close()
  }
}

describe('Evidence Studio spread', () => {
  it('stacks into one full-width column on a phone instead of overlapping', async () => {
    const { primary, secondary } = await layout(spread('evidence-studio'), 390)

    expect(primary.width).toBeGreaterThan(280)
    expect(secondary.top).toBeGreaterThanOrEqual(primary.bottom - 1)
    expect(secondary.right).toBeLessThanOrEqual(390)
  })

  it('keeps the source desk and output-mode rail side by side on a wide desktop', async () => {
    const { primary, secondary } = await layout(spread('evidence-studio'), 1440)

    expect(Math.abs(secondary.top - primary.top)).toBeLessThan(2)
    expect(secondary.left).toBeGreaterThanOrEqual(primary.right - 1)
    expect(secondary.width).toBeGreaterThanOrEqual(18 * 16 - 1)
  })

  it('still stacks the default spread on a phone', async () => {
    const { primary, secondary } = await layout(spread(), 390)

    expect(secondary.top).toBeGreaterThanOrEqual(primary.bottom - 1)
  })
})
