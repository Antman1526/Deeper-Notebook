import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeProvider } from './ThemeProvider'

const themeStore = vi.hoisted(() => ({
  theme: 'system' as 'light' | 'dark' | 'system',
  getSystemTheme: vi.fn<() => 'light' | 'dark'>(),
  getEffectiveTheme: vi.fn<() => 'light' | 'dark'>(),
}))

vi.mock('@/lib/stores/theme-store', () => ({
  useThemeStore: () => themeStore,
}))

describe('ThemeProvider catalog compatibility', () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    themeStore.theme = 'system'
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
})
