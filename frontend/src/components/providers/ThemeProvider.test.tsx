import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeProvider } from './ThemeProvider'

const themeStore = vi.hoisted(() => ({
  theme: 'system' as 'light' | 'dark' | 'system',
  legacyThemeOverride: false,
  setLegacyThemeOverride: vi.fn(),
  getSystemTheme: vi.fn<() => 'light' | 'dark'>(),
  getEffectiveTheme: vi.fn<() => 'light' | 'dark'>(),
}))

vi.mock('@/lib/stores/theme-store', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/stores/theme-store')>()
  return { ...actual, useThemeStore: () => themeStore }
})

describe('ThemeProvider catalog compatibility', () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    themeStore.theme = 'system'
    themeStore.legacyThemeOverride = false
    themeStore.setLegacyThemeOverride.mockReset()
    themeStore.getSystemTheme.mockReturnValue('dark')
    themeStore.getEffectiveTheme.mockReturnValue('dark')
  })

  afterEach(() => {
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    vi.clearAllMocks()
  })

  it('preserves a pre-hydrated catalog ID and derives dark mode from the catalog', () => {
    document.documentElement.dataset.theme = 'research-core-light'
    document.documentElement.classList.add('dark')

    render(<ThemeProvider><div>Research Core</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'research-core-light')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('keeps legacy system behavior when no catalog ID was pre-hydrated', () => {
    render(<ThemeProvider><div>Legacy system</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement).toHaveClass('dark')
  })

  it('keeps legacy explicit light behavior when no catalog ID was pre-hydrated', () => {
    themeStore.theme = 'light'
    themeStore.getEffectiveTheme.mockReturnValue('light')

    render(<ThemeProvider><div>Legacy light</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('normalizes a legacy stored light value through the catalog', () => {
    localStorage.setItem('dn-theme', 'light')

    render(<ThemeProvider><div>Stored legacy light</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('tracks system changes when the document only contains its legacy effective fallback', () => {
    const listeners: Array<(event: MediaQueryListEvent) => void> = []
    window.matchMedia = vi.fn(() => ({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addEventListener: (_type, listener) => listeners.push(listener as (event: MediaQueryListEvent) => void),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as MediaQueryList)
    document.documentElement.dataset.theme = 'dark'

    render(<ThemeProvider><div>Legacy system fallback</div></ThemeProvider>)
    themeStore.getSystemTheme.mockReturnValue('light')
    listeners.forEach(listener => listener({ matches: false } as MediaQueryListEvent))

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('keeps dn/onp persisted catalog selections stable across system changes', () => {
    const listeners: Array<(event: MediaQueryListEvent) => void> = []
    window.matchMedia = vi.fn(() => ({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addEventListener: (_type, listener) => listeners.push(listener as (event: MediaQueryListEvent) => void),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as MediaQueryList)

    for (const storageKey of ['dn-theme', 'onp-theme']) {
      localStorage.clear()
      localStorage.setItem(storageKey, 'research-core-light')
      document.documentElement.dataset.theme = 'dark'

      render(<ThemeProvider><div>Persisted catalog theme</div></ThemeProvider>)
      themeStore.getSystemTheme.mockReturnValue('dark')
      listeners.forEach(listener => listener({ matches: true } as MediaQueryListEvent))

      expect(document.documentElement).toHaveAttribute('data-theme', 'research-core-light')
      expect(document.documentElement).not.toHaveClass('dark')
    }
  })
})
