import { expect, test } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — in V2 every control has a 44px target, and checkboxes filled it: the
// Checkbox component rendered as a 44px filled square (Advanced, Settings, dialogs).
// It keeps the 44px target and draws a 16px box in its middle, aligned where a 16px
// box would sit.

test.beforeEach(async ({ page }) => {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
  await page.setViewportSize({ width: 1440, height: 900 })
})

test('a checked Checkbox is a 16px box inside a 44px target', async ({ page }) => {
  await page.goto('/advanced')
  const checkbox = page.getByRole('checkbox', { name: 'Sources' })
  await expect(checkbox).toBeChecked()
  const geometry = await checkbox.evaluate((element) => {
    const probe = document.createElement('span')
    probe.style.color = 'var(--primary)'
    document.body.appendChild(probe)
    const primary = getComputedStyle(probe).color
    probe.remove()
    const box = element.getBoundingClientRect()
    const own = getComputedStyle(element)
    const drawn = getComputedStyle(element, '::before')
    const heading = element.closest('div')!.parentElement!.querySelector('p, span, h3, h4, label')
    return {
      target: [Math.round(box.width), Math.round(box.height)],
      drawn: [drawn.width, drawn.height],
      ownBackground: own.backgroundColor,
      drawnBackground: drawn.backgroundColor,
      primary,
      drawnLeft: Math.round(box.left + (box.width - 16) / 2),
      columnLeft: Math.round(heading ? heading.getBoundingClientRect().left : -1),
    }
  })
  expect(Math.min(...geometry.target), JSON.stringify(geometry)).toBeGreaterThanOrEqual(44)
  expect(geometry.drawn, JSON.stringify(geometry)).toEqual(['16px', '16px'])
  // No 44px filled square: the control itself is transparent, the drawn box is filled.
  expect(geometry.ownBackground, JSON.stringify(geometry)).toBe('rgba(0, 0, 0, 0)')
  expect(geometry.drawnBackground, JSON.stringify(geometry)).toBe(geometry.primary)
  // The box lines up with the text column it sits in, not 14px inside it.
  expect(Math.abs(geometry.drawnLeft - geometry.columnLeft), JSON.stringify(geometry)).toBeLessThanOrEqual(2)

  // And keeps its usual gap to its label (a margin-based row spacing was lost).
  const gap = await page.evaluate(() => {
    const box = document.getElementById('sources')!.getBoundingClientRect()
    const label = document.querySelector('label[for="sources"]')!.getBoundingClientRect()
    return label.left - (box.left + (box.width - 16) / 2 + 16)
  })
  expect(gap).toBeGreaterThanOrEqual(6)
  expect(gap).toBeLessThanOrEqual(10)
})

test('the Checkbox still toggles and shows focus on the drawn box', async ({ page }) => {
  await page.goto('/advanced')
  const checkbox = page.getByRole('checkbox', { name: 'Notes' })
  await expect(checkbox).toBeChecked()
  await checkbox.focus()
  await page.keyboard.press('Space')
  await expect(checkbox).not.toBeChecked()
  const focus = await checkbox.evaluate((element) => ({
    own: getComputedStyle(element).outlineStyle,
    drawn: getComputedStyle(element, '::before').outlineStyle,
  }))
  expect(focus).toEqual({ own: 'none', drawn: 'solid' })
})
