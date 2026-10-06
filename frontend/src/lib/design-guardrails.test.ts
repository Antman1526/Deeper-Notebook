import fs from 'node:fs'
import path from 'node:path'
import { ESLint } from 'eslint'
import { beforeAll, describe, expect, it } from 'vitest'

// Phase 1 of the 2026-09-30 UI audit (4.4): consistency only holds if it is
// enforced. ESLint (`npm run lint`) rejects the patterns the codemod removed from
// TSX; the CSS half is scanned here because ESLint does not read stylesheets.

const frontend = path.resolve(__dirname, '../..')
const src = path.join(frontend, 'src')

// ESLint's first run loads the whole Next config; allow for a loaded machine.
describe('ESLint design rules', { timeout: 120_000 }, () => {
  let eslint: ESLint
  const lint = async (code: string, file = 'src/components/Example.tsx') => {
    const [result] = await eslint.lintText(code, { filePath: path.join(frontend, file) })
    return result.messages.filter((message) => message.ruleId === 'no-restricted-syntax').map((message) => message.message)
  }

  beforeAll(() => {
    eslint = new ESLint({ cwd: frontend })
  })

  it.each([
    ['a raw palette colour', `export const A = () => <p className="text-amber-700">x</p>`, /theme token/],
    ['a raw palette colour inside cn()', `import { cn } from '@/lib/utils'\nexport const A = ({ on }: { on: boolean }) => <p className={cn('p-2', on && 'bg-emerald-50')}>x</p>`, /theme token/],
    ['a raw palette colour in a template literal', 'export const A = ({ n }: { n: number }) => <p className={`p-${n} border-slate-200`}>x</p>', /theme token/],
    ['type below 12px', `export const A = () => <p className="text-[10px]">x</p>`, /12px/],
    ['a sub-12px rem size', `export const A = () => <p className="text-[0.68rem]">x</p>`, /12px/],
    ['transition-all', `export const A = () => <p className="transition-all">x</p>`, /transition-all/],
    ['a hover scale', `export const A = () => <button className="hover:scale-105">x</button>`, /scale/],
    ['a press scale', `export const A = () => <button className="active:scale-95">x</button>`, /scale/],
    ['a hex colour in className', `export const A = () => <p className="bg-[#2DD4BF]">x</p>`, /hex/],
    ['a hex colour in style', `export const A = () => <p style={{ color: '#2DD4BF' }}>x</p>`, /hex/],
  ])('rejects %s', async (_label, code, message) => {
    const messages = await lint(code)
    expect(messages.length, messages.join('\n')).toBeGreaterThan(0)
    expect(messages.join('\n')).toMatch(message)
  })

  it.each([
    ['status tokens', `export const A = () => <p className="bg-warning-soft text-warning-ink border-warning/40">x</p>`],
    ['12px type', `export const A = () => <p className="text-xs">x</p>`],
    ['named transitions', `export const A = () => <p className="transition-colors duration-200">x</p>`],
    ['the dialog zoom animation', `export const A = () => <p className="data-[state=open]:zoom-in-95">x</p>`],
    ['colour words that are not utilities', `export const A = () => <p title="Graphite gray-200 swatch">x</p>`],
  ])('allows %s', async (_label, code) => {
    expect(await lint(code)).toEqual([])
  })

  it('does not apply to tests, which assert on class names', async () => {
    expect(await lint(`export const cls = 'text-amber-700'`, 'src/components/Example.test.tsx')).toEqual([])
  })
})

// Every remaining !important is listed with its reason. Comments are ignored.
const IMPORTANT_ALLOWLIST: Record<string, { count: number; reason: string }> = {
  'app/globals.css': {
    count: 4,
    reason: 'prefers-reduced-motion must beat every transition and animation, including inline ones (WCAG 2.3.3)',
  },
  'components/vault/vault.css': {
    count: 4,
    reason: 'pre-existing phone-width override of the Research Core workspace track (not investigated in Phase 1)',
  },
}

const stylesheets = (dir: string): string[] =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return stylesheets(full)
    return entry.name.endsWith('.css') ? [full] : []
  })

const withoutComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')

describe('stylesheet guardrails', () => {
  const files = stylesheets(src).map((file) => ({
    file: path.relative(src, file),
    css: withoutComments(fs.readFileSync(file, 'utf8')),
  }))

  it('finds the stylesheets', () => {
    expect(files.map(({ file }) => file)).toContain('app/globals.css')
  })

  it.each(files)('$file uses !important only where allowlisted', ({ file, css }) => {
    const count = (css.match(/!important/g) ?? []).length
    expect(count, IMPORTANT_ALLOWLIST[file]?.reason ?? 'not allowlisted').toBe(IMPORTANT_ALLOWLIST[file]?.count ?? 0)
  })

  it.each(files)('$file never transitions every property', ({ css }) => {
    expect(css).not.toMatch(/transition(-property)?:\s*all\b/)
    expect(css).not.toMatch(/@apply[^;]*\btransition-all\b/)
  })

  // The same 12px floor the ESLint rule applies to text-[…] utilities.
  it.each(files)('$file sets no font size below 12px', ({ css }) => {
    const tooSmall = [...css.matchAll(/font-size:\s*([\d.]+)(rem|px)\b/g)]
      .filter(([, value, unit]) => Number(value) * (unit === 'rem' ? 16 : 1) < 12)
      .map(([declaration]) => declaration)
    expect(tooSmall).toEqual([])
  })
})
