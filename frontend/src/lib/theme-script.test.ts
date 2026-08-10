import { describe, expect, it, vi } from 'vitest'
import { themeScript } from './theme-script'

describe('pre-hydration Research Core theme script', () => {
  it('prefers canonical storage, then legacy, then old Zustand storage', () => {
    expect(themeScript.indexOf("getItem('dn-theme')")).toBeLessThan(themeScript.indexOf("getItem('onp-theme')"))
    expect(themeScript.indexOf("getItem('onp-theme')")).toBeLessThan(themeScript.indexOf("getItem('theme-storage')"))
  })

  it('falls back to Research Core Dark and sets dark class from the catalog', () => {
    expect(themeScript).toContain("'research-core-dark'")
    expect(themeScript).toContain('research-core-dark')
    expect(themeScript).toContain("classList.toggle('dark'")
  })

  it('normalizes legacy light values and rejects unknown theme IDs', () => {
    expect(themeScript).toContain("theme === 'light'")
    expect(themeScript).toContain("theme = 'light-blue'")
    expect(themeScript).toContain('validThemes.includes(theme)')
  })

  it.each([
    ['dark', 'dark'],
    ['system', 'dark'],
  ] as const)('prehydrates the canonical %s selection ahead of stale legacy storage', (selection, expectedTheme) => {
    const previousMatchMedia = window.matchMedia
    window.matchMedia = vi.fn(() => ({ matches: true }) as MediaQueryList)

    try {
      localStorage.clear()
      localStorage.setItem('dn-theme', selection)
      localStorage.setItem('onp-theme', 'light-blue')
      document.documentElement.dataset.theme = ''
      document.documentElement.className = ''

      window.eval(themeScript)

      expect(document.documentElement.dataset.theme).toBe(expectedTheme)
      expect(document.documentElement).toHaveClass('dark')
    } finally {
      window.matchMedia = previousMatchMedia
      localStorage.clear()
      document.documentElement.dataset.theme = ''
      document.documentElement.className = ''
    }
  })

  it('fails closed for malformed storage without deleting legacy theme data', () => {
    localStorage.clear()
    localStorage.setItem('onp-theme', 'archive-paper')
    localStorage.setItem('theme-storage', '{malformed')
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''

    window.eval(themeScript)

    expect(document.documentElement.dataset.theme).toBe('research-core-dark')
    expect(document.documentElement.dataset.dnWallpaper).toBe('aurora')
    expect(document.documentElement.dataset.dnMotion).toBe('system')
    expect(document.documentElement.dataset.dnTransparency).toBe('frosted')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
    expect(localStorage.getItem('theme-storage')).toBe('{malformed')
  })

  it('resolves system reduced motion before React hydration', () => {
    const previousMatchMedia = window.matchMedia
    window.matchMedia = vi.fn((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
    }) as MediaQueryList)

    try {
      localStorage.clear()
      localStorage.setItem(
        'dn-display-preferences-v1',
        JSON.stringify({
          state: { wallpaper: 'static', motion: 'system', transparency: 'solid' },
          version: 0,
        }),
      )
      document.documentElement.dataset.theme = ''
      document.documentElement.className = ''

      window.eval(themeScript)

      expect(document.documentElement.dataset.dnWallpaper).toBe('static')
      expect(document.documentElement.dataset.dnMotion).toBe('reduced')
      expect(document.documentElement.dataset.dnTransparency).toBe('solid')
    } finally {
      window.matchMedia = previousMatchMedia
      localStorage.clear()
      document.documentElement.dataset.theme = ''
      document.documentElement.className = ''
    }
  })
})
