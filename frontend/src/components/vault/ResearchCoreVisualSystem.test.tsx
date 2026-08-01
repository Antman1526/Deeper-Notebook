import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (file: string) => fs.readFileSync(
  path.resolve(__dirname, file),
  'utf8',
)

describe('Research Core visual system', () => {
  it('defines semantic deep-teal Research Core tokens without relying on raw component colors', () => {
    const globals = source('../../app/globals.css')

    for (const token of [
      '--research-canvas',
      '--research-panel',
      '--research-line',
      '--research-accent',
      '--research-accent-strong',
      '--research-warning',
      '--research-glow',
    ]) {
      expect(globals).toMatch(new RegExp(`${token}:`))
    }
  })

  it('ships responsive drawer and sequential mode hooks with a bounded entry transition', () => {
    const css = source('./vault.css')

    expect(css).toContain('.research-core-canvas')
    expect(css).toContain('.research-core-drawer-trigger')
    expect(css).toContain('.research-core-utility-drawer')
    expect(css).toContain('.research-core-intelligence-drawer')
    expect(css).toContain('@media (max-width: 1023px)')
    expect(css).toContain('@media (max-width: 719px)')
    expect(css).toMatch(/transition:\s*opacity\s+180ms/)
    expect(css).not.toMatch(/animation(?:-iteration-count)?\s*:\s*infinite/)
  })

  it('zeroes Research Core motion for reduced-motion users', () => {
    const css = `${source('../../app/globals.css')}\n${source('./vault.css')}`

    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toMatch(/animation-duration:\s*0\.01ms/)
    expect(css).toMatch(/transition-duration:\s*0\.01ms/)
  })
})
