import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTheme, useThemeStore } from '@/lib/stores/theme-store'
import { ThemeProvider } from './ThemeProvider'

function ThemeConsumer() {
  const { effectiveTheme } = useTheme()
  return <output data-testid="effective-theme">{effectiveTheme}</output>
}

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
    useThemeStore.setState({ theme: 'light', legacyThemeOverride: false, appliedTheme: 'light' })
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    useThemeStore.setState({ theme: 'system', legacyThemeOverride: false, appliedTheme: 'light' })
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

  it('resolves canonical persisted system and follows both OS directions', () => {
    localStorage.setItem('dn-theme', 'system')
    systemDark = true

    render(<ThemeProvider><div>Research Core</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(addEventListener).toHaveBeenCalledTimes(1)

    systemDark = false
    dispatchSystemChange()

    expect(document.documentElement).toHaveAttribute('data-theme', 'light-blue')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(addEventListener).toHaveBeenCalledTimes(1)
  })

  it('updates a useTheme consumer through the provider without a second OS listener', () => {
    localStorage.setItem('dn-theme', 'system')
    useThemeStore.setState({ theme: 'system', legacyThemeOverride: false, appliedTheme: 'light' })

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('effective-theme')).toHaveTextContent('light')
    expect(addEventListener).toHaveBeenCalledTimes(1)

    systemDark = true
    dispatchSystemChange()

    expect(screen.getByTestId('effective-theme')).toHaveTextContent('dark')
    expect(addEventListener).toHaveBeenCalledTimes(1)
  })

  it('keeps an explicit persisted catalog theme fixed without an OS listener', () => {
    localStorage.setItem('dn-theme', 'research-core-light')
    systemDark = true

    render(<ThemeProvider><div>Research Core</div></ThemeProvider>)

    expect(document.documentElement).toHaveAttribute('data-theme', 'research-core-light')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(addEventListener).not.toHaveBeenCalled()

    systemDark = false
    dispatchSystemChange()

    expect(document.documentElement).toHaveAttribute('data-theme', 'research-core-light')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(removeEventListener).not.toHaveBeenCalled()
  })

  it('removes the sole system listener when the globally mounted provider unmounts', () => {
    localStorage.setItem('dn-theme', 'system')
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
