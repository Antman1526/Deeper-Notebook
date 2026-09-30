import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Tailwind v4 does not read tailwind.config.ts unless the CSS opts in with
// `@config`. Anything the old config used to provide (the typography plugin,
// `darkMode: "class"`) must therefore be declared in CSS itself, or the
// utilities silently compile to nothing / to the wrong media query.
const css = fs.readFileSync(path.resolve(__dirname, 'globals.css'), 'utf8')

describe('globals.css Tailwind v4 contract', () => {
  it('loads the typography plugin so `prose` classes generate rules', () => {
    expect(css).toMatch(/@plugin\s+["']@tailwindcss\/typography["']\s*;/)
  })

  it('binds `dark:` to the .dark class the theme script toggles, not prefers-color-scheme', () => {
    expect(css).toMatch(/@custom-variant\s+dark\s*\(\s*&:where\(\s*\.dark\s*,\s*\.dark \*\s*\)\s*\)\s*;/)
  })

  it('maps prose colors to theme tokens so prose text follows the active theme', () => {
    expect(css).toMatch(/\.prose\s*\{[^}]*--tw-prose-body:\s*var\(--foreground\)/)
    expect(css).toMatch(/\.prose\s*\{[^}]*--tw-prose-links:\s*var\(--primary\)/)
  })

  // Tailwind inlines a shadow value into each utility, so a `.dark` override of
  // a token that was only declared in plain CSS never reached `shadow-*`. Mapping
  // the theme key to a var() makes Tailwind emit `--tw-shadow: var(--elevation-X)`
  // for every variant (shadow-md, hover:shadow-md, shadow-md/30), and the `.dark`
  // block then changes the real shadow by ordinary cascade.
  it.each(['xs', 'sm', 'md', 'lg', 'xl'])('maps shadow-%s to its themeable elevation token', (step) => {
    expect(css).toMatch(new RegExp(`@theme inline \\{[\\s\\S]*?--shadow-${step}:\\s*var\\(--elevation-${step}\\)`))
  })

  it('gives dark themes their own, stronger elevation values', () => {
    const dark = css.slice(css.indexOf('.dark {'), css.indexOf('html[data-theme]'))
    expect(dark).toMatch(/--elevation-md:\s*0 4px 6px -1px rgba\(0, 0, 0, 0\.5\)/)
  })

  it('no longer declares the old plain --shadow-* values that nothing could apply', () => {
    expect(css).not.toMatch(/^\s*--shadow-(xs|sm|md|lg|xl):\s*0 /m)
  })

  it('suppresses the plugin backticks around inline code', () => {
    expect(css).toMatch(/\.prose code::before,\s*\.prose code::after\s*\{\s*content:\s*none;/)
  })
})
