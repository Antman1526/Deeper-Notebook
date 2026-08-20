import { afterEach, describe, expect, it, vi } from 'vitest'
import { themeScript } from './theme-script'

describe('pre-hydration Gemini-forward theme script', () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
  })

  it('prefers canonical storage, then legacy, then old Zustand storage', () => {
    expect(themeScript.indexOf("getItem('dn-theme')")).toBeLessThan(themeScript.indexOf("getItem('onp-theme')"))
    expect(themeScript.indexOf("getItem('onp-theme')")).toBeLessThan(themeScript.indexOf("getItem('theme-storage')"))
  })

  it('uses the Gemini-forward default and retains the dark catalog contract', () => {
    expect(themeScript).toContain("'gemini-forward-light'")
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

    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(document.documentElement.dataset.dnWallpaper).toBe('aurora')
    expect(document.documentElement.dataset.dnMotion).toBe('system')
    expect(document.documentElement.dataset.dnTransparency).toBe('frosted')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
    expect(localStorage.getItem('theme-storage')).toBe('{malformed')
  })

  it.each([
    ['1', 'gemini-forward-light'],
    ['0', 'research-core-dark'],
  ] as const)('uses the build-time %s fresh default with empty storage', async (flag, expectedTheme) => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = flag
    vi.resetModules()
    const { themeScript: buildThemeScript } = await import('./theme-script')

    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    window.eval(buildThemeScript)

    expect(document.documentElement.dataset.theme).toBe(expectedTheme)
    expect(document.documentElement.classList.contains('dark')).toBe(expectedTheme === 'research-core-dark')
  })

  it.each(['1', '0'] as const)('preserves an explicit archive-paper selection in build %s', async flag => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = flag
    vi.resetModules()
    const { themeScript: buildThemeScript } = await import('./theme-script')

    localStorage.clear()
    localStorage.setItem('dn-theme', 'archive-paper')
    localStorage.setItem('onp-theme', 'research-core-dark')
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    window.eval(buildThemeScript)

    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
    expect(localStorage.getItem('onp-theme')).toBe('research-core-dark')
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

  it('prehydrates the persisted Focus mode root contract without changing theme state', () => {
    localStorage.clear()
    localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({
        state: { wallpaper: 'static', motion: 'system', transparency: 'solid', focusMode: true },
        version: 0,
      }),
    )
    document.documentElement.dataset.theme = 'research-core-dark'
    document.documentElement.dataset.dnFocusMode = 'false'

    window.eval(themeScript)

    expect(document.documentElement.dataset.theme).toBe('gemini-forward-light')
    expect(document.documentElement.dataset.dnFocusMode).toBe('true')
  })

  it('fails closed to inactive Focus mode for malformed persisted values', () => {
    localStorage.clear()
    localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({ state: { focusMode: 'yes' }, version: 0 }),
    )
    document.documentElement.dataset.dnFocusMode = 'true'

    window.eval(themeScript)

    expect(document.documentElement.dataset.dnFocusMode).toBe('false')
  })
})
