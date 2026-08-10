import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { THEME_CATALOG } from '@/lib/themes/catalog'

const source = (file: string) => fs.readFileSync(
  path.resolve(__dirname, file),
  'utf8',
)

describe('Research Core visual system', () => {
  it('defines semantic deep-teal Research Core tokens without relying on raw component colors', () => {
    const globals = source('../../app/globals.css')
    const tokens = source('../deeper-notebook/tokens.css')

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

    for (const token of [
      '--dn-canvas', '--dn-panel', '--dn-panel-raised', '--dn-separator',
      '--dn-focus', '--dn-selection', '--dn-evidence', '--dn-warning',
      '--dn-editable', '--dn-read-only', '--dn-model-local', '--dn-model-cloud',
      '--dn-graph-node', '--dn-graph-edge', '--dn-graph-selected',
    ]) {
      expect(tokens).toMatch(new RegExp(`${token}:`))
    }
  })

  it('maps catalog light themes onto light semantic surfaces', () => {
    const globals = source('../../app/globals.css')

    expect(globals).toContain('html[data-theme="research-core-light"]')
    expect(globals).toContain('--dn-theme-canvas: #F5FBF9;')
    expect(globals).toContain('--dn-theme-text: #102A2A;')
    expect(globals).toContain('html[data-theme="archive-paper"]')
    expect(globals).toContain('--dn-theme-canvas: #F7F1E5;')
    expect(globals).toContain('html[data-theme="high-contrast-light"]')
    expect(globals).toContain('--dn-theme-canvas: #FFFFFF;')
    expect(globals).toMatch(/html\[data-theme\]\s*\{[\s\S]*--background:\s*var\(--dn-theme-canvas\)/)
    expect(globals).toMatch(/html\[data-theme\]\s*\{[\s\S]*--foreground:\s*var\(--dn-theme-text\)/)
  })

  it('uses contrast-safe accent foregrounds for every catalog theme', () => {
    const globals = source('../../app/globals.css')

    for (const theme of THEME_CATALOG) {
      const selector = new RegExp(
        `html\\[data-theme="${theme.id}"\\]\\s*\\{([^}]*)\\}`,
      ).exec(globals)
      expect(selector?.[1]).toMatch(/--dn-theme-accent-foreground:\s*#[0-9A-F]{6}/)

      const foreground = /--dn-theme-accent-foreground:\s*(#[0-9A-F]{6})/.exec(selector?.[1] ?? '')?.[1]
      expect(foreground).toBeDefined()
      expect(contrastRatio(theme.preview.accent, foreground as string)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('ships responsive drawer and sequential mode hooks with a bounded entry transition', () => {
    const css = source('./vault.css')

    expect(css).toContain('.research-core-canvas')
    expect(css).toContain('.research-core-folio')
    expect(css).toContain('.research-core-folio__spread')
    expect(css).toContain('.research-core-authority')
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

function contrastRatio(first: string, second: string): number {
  const luminance = (value: string) => {
    const channels = [1, 3, 5].map(offset => parseInt(value.slice(offset, offset + 2), 16) / 255)
    const linear = channels.map(channel => (
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    ))
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
  }

  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (lighter + 0.05) / (darker + 0.05)
}
