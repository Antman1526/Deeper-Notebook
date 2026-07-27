import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { BRAND } from './brand'

const REPOSITORY_ROOT = path.resolve(__dirname, '../../..')
const FRONTEND_SRC = path.join(REPOSITORY_ROOT, 'frontend/src')
const COMPONENT_ROOT = path.join(FRONTEND_SRC, 'components')
const LEGACY_COMPONENT_NAMESPACE = ['components', 'onp'].join('/')
const LEGACY_TOKEN_PREFIX = `--${['on', 'p'].join('')}-`
const LEGACY_VISUAL_CLASS = new RegExp(
  `\\b${['on', 'p'].join('')}-(?:glass|aurora(?:-[a-z0-9-]+)?)\\b`,
)

const CANONICAL_MARK = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-labelledby="title">
  <title id="title">Deeper Notebook</title>
  <defs>
    <linearGradient id="core" x1="48" y1="36" x2="210" y2="220" gradientUnits="userSpaceOnUse">
      <stop stop-color="#2DD4BF"/>
      <stop offset="1" stop-color="#38BDF8"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="58" fill="#071B1D"/>
  <path d="M63 53h101c18 0 29 11 29 29v119H91c-16 0-28-12-28-28V53Z"
        fill="#0F766E" stroke="url(#core)" stroke-width="12" stroke-linejoin="round"/>
  <path d="M91 53v148" stroke="#CCFBF1" stroke-width="10" stroke-linecap="round" opacity=".9"/>
  <path d="m157 82 8 23 23 8-23 8-8 23-8-23-23-8 23-8 8-23Z" fill="#CCFBF1"/>
  <circle cx="157" cy="113" r="10" fill="#38BDF8"/>
</svg>
`

function normalizeSvg(svg: string) {
  return svg.trim().replace(/\s+/g, ' ')
}

function sourceFiles(root: string): string[] {
  return fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = path.join(root, entry.name)
    if (entry.isDirectory()) return sourceFiles(absolutePath)
    if (!/\.(?:css|md|ts|tsx)$/.test(entry.name)) return []
    if (absolutePath === __filename) return []
    return [absolutePath]
  })
}

describe('Deeper Notebook brand', () => {
  it('exposes the approved identity and Research Core palette', () => {
    expect(BRAND.name).toBe('Deeper Notebook')
    expect(BRAND.tagline).toBe('Think further with every source')
    expect(BRAND.colors).toEqual({
      deep: '#071B1D',
      darkTeal: '#0F766E',
      teal: '#2DD4BF',
      cyan: '#38BDF8',
      light: '#CCFBF1',
    })
  })

  it('uses the exact accessible Notebook Spark vector as both SVG sources', () => {
    for (const svgPath of [
      path.join(REPOSITORY_ROOT, 'brand/deeper-notebook-mark.svg'),
      path.join(REPOSITORY_ROOT, 'frontend/public/logo.svg'),
    ]) {
      expect(normalizeSvg(fs.readFileSync(svgPath, 'utf8'))).toBe(
        normalizeSvg(CANONICAL_MARK),
      )
    }
  })

  it('uses Research Core defaults while retaining semantic theme variables', () => {
    const globals = fs.readFileSync(
      path.join(FRONTEND_SRC, 'app/globals.css'),
      'utf8',
    )

    expect(globals).toContain('--dn-deep: #071B1D;')
    expect(globals).toContain('--dn-dark-teal: #0F766E;')
    expect(globals).toContain('--dn-teal: #2DD4BF;')
    expect(globals).toContain('--dn-cyan: #38BDF8;')
    expect(globals).toContain('--dn-light: #CCFBF1;')
    expect(globals).toContain('--background: var(--dn-deep);')
    expect(globals).toContain('--foreground: var(--dn-light);')
    expect(globals).toContain('--primary: var(--dn-teal);')
    expect(globals).toContain('--primary-foreground: var(--dn-deep);')
    expect(globals).toContain('--ring: var(--dn-cyan);')
  })

  it('preserves the global reduced-motion guard', () => {
    const globals = fs.readFileSync(
      path.join(FRONTEND_SRC, 'app/globals.css'),
      'utf8',
    )

    expect(globals).toMatch(
      /@media \(prefers-reduced-motion: reduce\)[\s\S]*animation-duration: 0\.01ms !important;[\s\S]*transition-duration: 0\.01ms !important;/,
    )
  })

  it('moves the component layer and removes its legacy import and CSS namespaces', () => {
    expect(
      fs.existsSync(path.join(COMPONENT_ROOT, 'deeper-notebook')),
    ).toBe(true)
    expect(fs.existsSync(path.join(COMPONENT_ROOT, 'onp'))).toBe(false)

    const violations = sourceFiles(FRONTEND_SRC).flatMap((filePath) => {
      const source = fs.readFileSync(filePath, 'utf8')
      const reasons = [
        source.includes(LEGACY_COMPONENT_NAMESPACE) && 'component path',
        source.includes(LEGACY_TOKEN_PREFIX) && 'token prefix',
        LEGACY_VISUAL_CLASS.test(source) && 'visual class',
      ].filter(Boolean)
      return reasons.map((reason) => ({
        file: path.relative(FRONTEND_SRC, filePath),
        reason,
      }))
    })

    expect(violations).toEqual([])
  })

  it('keeps the moved visual tokens derived from live theme semantics', () => {
    const tokens = fs.readFileSync(
      path.join(COMPONENT_ROOT, 'deeper-notebook/tokens.css'),
      'utf8',
    )

    expect(tokens).toContain('--dn-accent-soft: color-mix(in oklab, var(--primary)')
    expect(tokens).toContain('--dn-aurora-1: var(--primary, #2DD4BF);')
    expect(tokens).toContain('--dn-aurora-2: var(--accent, #38BDF8);')
    expect(tokens).toContain('animation: dn-aurora-drift 26s ease-in-out infinite alternate;')
  })
})
