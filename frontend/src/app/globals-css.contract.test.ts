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

  it('suppresses the plugin backticks around inline code', () => {
    expect(css).toMatch(/\.prose code::before,\s*\.prose code::after\s*\{\s*content:\s*none;/)
  })
})
