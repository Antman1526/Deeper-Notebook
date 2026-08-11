import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const shellCss = fs.readFileSync(path.resolve(__dirname, 'shell.css'), 'utf8')

describe('Focus shell CSS contracts', () => {
  it('keeps the real legacy sidebar compact and the main route usable on mobile', () => {
    const mobileFocusCss = shellCss.slice(shellCss.lastIndexOf('@media (max-width: 1023px)'))
    const mobileFocusRule = /html\[data-dn-focus-mode="true"\] \.dn-legacy-shell > \.app-sidebar\s*\{([\s\S]*?)\}/
    const match = mobileFocusRule.exec(mobileFocusCss)

    expect(match?.[1] ?? '').toMatch(/display:\s*flex/)
    expect(match?.[1] ?? '').toMatch(/width:\s*var\(--dn-focus-rail\)/)
    expect(mobileFocusCss).toMatch(/html\[data-dn-focus-mode="true"\] \.dn-legacy-shell > main\s*\{[\s\S]*?width:\s*auto/)
  })

  it('overrides the compact Research Core navigator release rule while Focus is active', () => {
    const selector = 'html[data-dn-focus-mode="true"] .dn-luminous-workspace:has(.research-core-canvas) > .dn-adaptive-navigator'
    const selectorIndex = shellCss.indexOf(selector)
    const declarationEnd = shellCss.indexOf('}', selectorIndex)
    const declaration = selectorIndex >= 0 && declarationEnd >= 0
      ? shellCss.slice(selectorIndex, declarationEnd)
      : ''

    expect(selectorIndex).toBeGreaterThan(-1)
    expect(declaration).toMatch(/display:\s*block/)
  })
})
