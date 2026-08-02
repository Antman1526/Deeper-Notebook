import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isThemeId } from '@/lib/themes/catalog'
import { useThemeStore } from './theme-store'

describe('legacy theme-store catalog authority', () => {
  let systemDark = false
  let mediaListeners: Array<(event: MediaQueryListEvent) => void> = []

  beforeEach(() => {
    systemDark = false
    mediaListeners = []
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    window.matchMedia = vi.fn(() => ({
      get matches() { return systemDark },
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addEventListener: (_type, listener) => mediaListeners.push(listener as (event: MediaQueryListEvent) => void),
      removeEventListener: (_type, listener) => {
        mediaListeners = mediaListeners.filter(candidate => candidate !== listener)
      },
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as MediaQueryList)
    useThemeStore.setState({ theme: 'system' })
  })

  afterEach(() => {
    useThemeStore.getState().setTheme('light')
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
  })

  it('normalizes the direct legacy light setter to a semantic catalog theme', () => {
    useThemeStore.getState().setTheme('light')

    expect(document.documentElement.dataset.theme).toBe('light-blue')
    expect(isThemeId(document.documentElement.dataset.theme)).toBe(true)
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('maps legacy system changes through catalog IDs when no explicit catalog theme exists', () => {
    useThemeStore.getState().setTheme('system')
    expect(document.documentElement.dataset.theme).toBe('light-blue')
    expect(document.documentElement).not.toHaveClass('dark')

    systemDark = true
    mediaListeners.forEach(listener => listener({ matches: true } as MediaQueryListEvent))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
  })

  it('lets a new legacy setter override stale catalog storage', () => {
    localStorage.setItem('dn-theme', 'archive-paper')

    useThemeStore.getState().setTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light-blue')

    useThemeStore.getState().setTheme('system')
    systemDark = true
    mediaListeners.forEach(listener => listener({ matches: true } as MediaQueryListEvent))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
  })

})
