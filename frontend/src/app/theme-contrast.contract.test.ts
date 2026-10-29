import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { THEME_CATALOG } from '@/lib/themes/catalog'

// v0.8.130 — text-on-fill contrast for every theme, read from the source of
// globals.css (no browser). Each scope is the cascade the browser applies on
// <html>: `:root`, then `.dark` for dark themes, then the shared
// `html[data-theme]` block, then the theme's own block. var() chains are
// resolved within that scope; hex, oklch() and `color-mix(in oklab, X N%,
// transparent)` are evaluated here, and anything else fails loudly instead of
// being skipped. Translucent colours are composited over the scope's --card,
// as e2e/theme-contract.spec.ts does in the real build.

const css = fs.readFileSync(path.resolve(__dirname, 'globals.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

type Decls = Record<string, string>
const declarations = (body: string): Decls =>
  Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))
const block = (selector: string): Decls => {
  const start = css.indexOf(`${selector} {`)
  expect(start, `${selector} block exists`).toBeGreaterThanOrEqual(0)
  return declarations(css.slice(start + selector.length + 2, css.indexOf('}', start)))
}
const themeBlocks = new Map(
  [...css.matchAll(/html\[data-theme="([^"]+)"\]\s*\{([^}]*)\}/g)].map((m) => [m[1], declarations(m[2])]),
)

// --- WCAG 2.x contrast. Colours are [r, g, b, alpha], channels gamma-encoded 0..1.
type Rgba = [number, number, number, number]
const linear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const encode = (c: number) => {
  const v = Math.min(1, Math.max(0, c))
  return v <= 0.0031308 ? v * 12.92 : 1.055 * v ** (1 / 2.4) - 0.055
}
const luminance = ([r, g, b]: Rgba) => 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
const contrast = (a: Rgba, b: Rgba) => {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high + 0.05) / (low + 0.05)
}
const oklab = (l: number, a: number, b: number): Rgba => {
  const lms = [
    l + 0.3963377774 * a + 0.2158037573 * b,
    l - 0.1055613458 * a - 0.0638541728 * b,
    l - 0.0894841775 * a - 1.291485548 * b,
  ].map((v) => v ** 3)
  return [
    encode(4.0767416621 * lms[0] - 3.3077115913 * lms[1] + 0.2309699292 * lms[2]),
    encode(-1.2684380046 * lms[0] + 2.6097574011 * lms[1] - 0.3413193965 * lms[2]),
    encode(-0.0041960863 * lms[0] - 0.7034186147 * lms[1] + 1.707614701 * lms[2]),
    1,
  ]
}
const toOklab = ([r, g, b]: Rgba): [number, number, number] => {
  const [lr, lg, lb] = [r, g, b].map(linear)
  const [l, m, s] = [
    0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb,
    0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb,
    0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb,
  ].map(Math.cbrt)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}
const oklch = (l: number, c: number, hDeg: number): Rgba =>
  oklab(l, c * Math.cos((hDeg * Math.PI) / 180), c * Math.sin((hDeg * Math.PI) / 180))
const over = ([r, g, b, a]: Rgba, [br, bg, bb]: Rgba): Rgba => [
  r * a + br * (1 - a),
  g * a + bg * (1 - a),
  b * a + bb * (1 - a),
  1,
]

function color(value: string, scope: Decls, trail: string[]): Rgba {
  const v = value.trim()
  const ref = /^var\((--[\w-]+)\)$/.exec(v)
  if (ref) {
    if (trail.includes(ref[1])) throw new Error(`cycle: ${[...trail, ref[1]].join(' -> ')}`)
    if (!(ref[1] in scope)) throw new Error(`${trail.join(' -> ')} -> ${ref[1]} is not defined in this scope`)
    return color(scope[ref[1]], scope, [...trail, ref[1]])
  }
  const hex = /^#([0-9a-f]{6})$/i.exec(v)
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16) / 255).concat(1) as Rgba
  const lch = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(v)
  if (lch) return oklch(Number(lch[1]), Number(lch[2]), Number(lch[3]))
  const tint = /^color-mix\(in oklab,\s*(.+?)\s+([\d.]+)%,\s*transparent\)$/.exec(v)
  if (tint) {
    const [r, g, b, a] = color(tint[1], scope, trail)
    return [r, g, b, (a * Number(tint[2])) / 100]
  }
  const mix = /^color-mix\(in oklab,\s*(.+?)\s+([\d.]+)%,\s*(.+?)\)$/.exec(v)
  if (mix) {
    const [first, second] = [toOklab(color(mix[1], scope, trail)), toOklab(color(mix[3], scope, trail))]
    const w = Number(mix[2]) / 100
    return oklab(...(first.map((c, i) => c * w + second[i] * (1 - w)) as [number, number, number]))
  }
  throw new Error(`${trail.join(' -> ')} = "${v}" is not a colour this test can resolve`)
}

const PAIRS = [
  ['--primary', '--primary-foreground'],
  ['--brand-accent', '--brand-accent-foreground'],
  ['--accent', '--accent-foreground'],
  ['--destructive', '--destructive-foreground'],
  ['--sidebar-primary', '--sidebar-primary-foreground'],
] as const

// Pairs that cannot pass by changing the foreground alone (fixing them means
// changing the fill, which is a design decision). Format:
//   { scope: 'theme-id', fill: '--primary', ratio: 3.2 }, // why it is accepted
// Currently none.
const KNOWN_EXCEPTIONS: { scope: string; fill: string; ratio: number }[] = []

const base = block(':root')
const scopes: [string, Decls][] = [
  [':root', base],
  ['.dark', { ...base, ...block('.dark') }],
  ...THEME_CATALOG.map((theme): [string, Decls] => [
    theme.id,
    {
      ...base,
      ...(theme.dark ? block('.dark') : {}),
      ...block('html[data-theme]'),
      ...(themeBlocks.get(theme.id) ?? {}),
    },
  ]),
]

describe('theme text-on-fill contrast (WCAG 4.5:1)', () => {
  it('has a globals.css block for every catalog theme, and no block outside the catalog', () => {
    expect([...themeBlocks.keys()].sort()).toEqual(THEME_CATALOG.map((theme) => theme.id).sort())
  })

  const cases = scopes.flatMap(([scope, decls]) => PAIRS.map(([fill, fg]) => [scope, fill, fg, decls] as const))
  it.each(cases)('%s: %s / %s', (scope, fill, fg, decls) => {
    const card = color(decls['--card'], decls, ['--card'])
    const fillColor = over(color(decls[fill] ?? `var(${fill})`, decls, [fill]), card)
    const fgColor = over(color(decls[fg] ?? `var(${fg})`, decls, [fg]), fillColor)
    const ratio = contrast(fillColor, fgColor)
    const exception = KNOWN_EXCEPTIONS.find((e) => e.scope === scope && e.fill === fill)
    if (exception) {
      expect(ratio, `${scope} ${fill} exception is still accurate`).toBeCloseTo(exception.ratio, 1)
      return
    }
    expect(ratio, `${scope}: ${fg} on ${fill} = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5)
  })
})
