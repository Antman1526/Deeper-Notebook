import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useThemeStore } from '@/lib/stores/theme-store'
import { ThemeProvider } from './ThemeProvider'

describe('ThemeProvider legacy system ownership', () => {
  let systemDark = false
  let listeners: Array<(event: MediaQueryListEvent) => void> = []
  let addEventListener: ReturnType<typeof vi.fn>
  let removeEventListener: ReturnType<typeof vi.fn>
  let dispatchSystemChange: () => void

  beforeEach(() => {
    systemDark = false
    listeners = []
    addEventListener = vi.fn((_type, listener) => listeners.push(listener as (event: MediaQueryListEvent) => void))
    removeEventListener = vi.fn((_type, listener) => {
      listeners = listeners.filter(candidate => candidate !== listener)
    })
    dispatchSystemChange = () => act(() => {
      listeners.forEach(listener => listener({ matches: systemDark } as MediaQueryListEvent))
    })
    window.matchMedia = vi.fn(() => ({
      get matches() { return systemDark },
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addEventListener,
      removeEventListener,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as MediaQueryList)
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    useThemeStore.setState({ theme: 'light', legacyThemeOverride: false })
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    useThemeStore.setState({ theme: 'system', legacyThemeOverride: false })
  })

  it('uses one provider-owned listener for direct system changes and removes it when switching away', () => {
    render(<ThemeProvider><div>Research Core</div></ThemeProvider>)

    act(() => useThemeStore.getState().setTheme('system'))

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(addEventListener).toHaveBeenCalledTimes(1)

    systemDark = true
    dispatchSystemChange()

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement).toHaveClass('dark')

    act(() => useThemeStore.getState().setTheme('light'))

    expect(removeEventListener).toHaveBeenCalledTimes(1)
    expect(listeners).toEqual([])
    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')

    systemDark = true
    dispatchSystemChange()

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('removes the sole system listener when the globally mounted provider unmounts', () => {
    useThemeStore.setState({ theme: 'system', legacyThemeOverride: false })
    const view = render(<ThemeProvider><div>Research Core</div></ThemeProvider>)

    expect(addEventListener).toHaveBeenCalledTimes(1)
    view.unmount()

    expect(removeEventListener).toHaveBeenCalledTimes(1)
    expect(listeners).toEqual([])
    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')

    systemDark = true
    dispatchSystemChange()

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
  })
})
