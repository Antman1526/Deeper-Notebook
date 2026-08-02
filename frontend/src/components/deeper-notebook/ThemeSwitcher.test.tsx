import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { THEME_SELECTION_CHANGE_EVENT } from '@/lib/theme-storage'

const { deeperNotebookFetch } = vi.hoisted(() => ({
  deeperNotebookFetch: vi.fn(),
}))

interface ChildrenProps {
  children?: ReactNode
}

interface MenuItemProps extends ChildrenProps {
  onClick?: () => void
  'aria-current'?: 'true'
}

vi.mock('@/lib/api/deeper-notebook', () => ({ deeperNotebookFetch }))
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: ChildrenProps) => children,
  DropdownMenuTrigger: ({ children }: ChildrenProps) => children,
  DropdownMenuContent: ({ children }: ChildrenProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, ...props }: MenuItemProps) => <button onClick={onClick} {...props}>{children}</button>,
  DropdownMenuLabel: ({ children }: ChildrenProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
}))

import { ThemeSwitcher } from './ThemeSwitcher'
import { ThemeGallery } from './ThemeGallery'

type ThemeBridge = { setTheme: ReturnType<typeof vi.fn> }
type ThemeWindow = Window & { DN?: ThemeBridge; ONP?: ThemeBridge }

function selectDarkTheme() {
  fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
}

describe('ThemeSwitcher Deeper Notebook compatibility', () => {
  beforeEach(() => {
    deeperNotebookFetch.mockResolvedValue({
      json: async () => ({ theme: 'light-blue' }),
    })
  })

  afterEach(() => {
    delete (window as ThemeWindow).DN
    delete (window as ThemeWindow).ONP
    document.documentElement.dataset.theme = ''
    localStorage.clear()
    deeperNotebookFetch.mockReset()
    vi.restoreAllMocks()
  })

  it('uses the canonical DN bridge when it is the only desktop bridge', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical

    render(<ThemeSwitcher />)
    selectDarkTheme()

    expect(canonical.setTheme).toHaveBeenCalledWith('dark')
  })

  it('falls back to the legacy ONP bridge when the canonical bridge is absent', () => {
    const legacy = { setTheme: vi.fn() }
    ;(window as ThemeWindow).ONP = legacy

    render(<ThemeSwitcher />)
    selectDarkTheme()

    expect(legacy.setTheme).toHaveBeenCalledWith('dark')
  })

  it('gives the canonical DN bridge precedence over the legacy ONP bridge', () => {
    const canonical = { setTheme: vi.fn() }
    const legacy = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical
    ;(window as ThemeWindow).ONP = legacy

    render(<ThemeSwitcher />)
    selectDarkTheme()

    expect(canonical.setTheme).toHaveBeenCalledWith('dark')
    expect(legacy.setTheme).not.toHaveBeenCalled()
  })

  it('persists a selected theme under the canonical key and mirrors it', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical

    render(<ThemeSwitcher />)
    selectDarkTheme()

    expect(localStorage.getItem('dn-theme')).toBe('dark')
    expect(localStorage.getItem('onp-theme')).toBe('dark')
  })

  it('migrates legacy theme storage into the canonical key', () => {
    localStorage.setItem('onp-theme', 'midnight-aurora')

    render(<ThemeSwitcher />)

    expect(localStorage.getItem('dn-theme')).toBe('midnight-aurora')
  })

  it('gives canonical theme storage precedence over legacy storage', () => {
    localStorage.setItem('dn-theme', 'dark')
    localStorage.setItem('onp-theme', 'midnight-aurora')

    render(<ThemeSwitcher />)

    expect(localStorage.getItem('dn-theme')).toBe('dark')
  })

  it('shows all catalog groups and applies Research Core Light canonically', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical

    render(<ThemeSwitcher />)

    expect(screen.getByText('Featured')).toBeVisible()
    expect(screen.getByText('Light')).toBeVisible()
    expect(screen.getAllByText('Dark')).toHaveLength(2)
    expect(screen.getByText('Accessibility')).toBeVisible()
    expect(screen.getByText('Classics')).toBeVisible()
    expect(screen.getAllByRole('button')).toHaveLength(26)

    fireEvent.click(screen.getByRole('button', { name: 'Research Core Light' }))

    expect(canonical.setTheme).toHaveBeenCalledWith('research-core-light')
    expect(localStorage.getItem('dn-theme')).toBe('research-core-light')
  })

  it('exposes the compact current theme to assistive technology', () => {
    document.documentElement.dataset.theme = 'dark'

    render(<ThemeSwitcher />)

    expect(screen.getByRole('button', { name: 'Dark Current theme' })).toHaveAttribute('aria-current', 'true')
  })

  it('prefers persisted system selection over its resolved dark document palette', () => {
    localStorage.setItem('dn-theme', 'system')
    document.documentElement.dataset.theme = 'dark'

    render(<ThemeSwitcher />)

    expect(screen.getByRole('button', { name: 'System Current theme' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: 'Dark' })).not.toHaveAttribute('aria-current')
  })

  it('synchronizes current selection and the gallery restore baseline across pickers', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical
    localStorage.setItem('dn-theme', 'research-core-dark')

    const addListener = vi.spyOn(window, 'addEventListener')
    const removeListener = vi.spyOn(window, 'removeEventListener')
    const view = render(
      <>
        <ThemeSwitcher />
        <ThemeGallery />
      </>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Apply Archive Paper' }))
    expect(screen.getByRole('button', { name: 'Archive Paper Current theme' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('article', { name: 'Archive Paper theme' })).toHaveTextContent('Current')

    fireEvent.click(screen.getByRole('button', { name: 'Preview Research Core Light' }))
    fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
    expect(screen.getByRole('button', { name: 'Dark Current theme' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('article', { name: 'Dark theme' })).toHaveTextContent('Current')
    expect(screen.queryByRole('button', { name: 'Restore previous theme' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Preview Research Core Light' }))
    fireEvent.click(screen.getByRole('button', { name: 'Restore previous theme' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('article', { name: 'Dark theme' })).toHaveTextContent('Current')

    view.unmount()
    const selectionAdds = addListener.mock.calls.filter(([type]) => type === THEME_SELECTION_CHANGE_EVENT)
    const selectionRemoves = removeListener.mock.calls.filter(([type]) => type === THEME_SELECTION_CHANGE_EVENT)
    expect(selectionAdds).toHaveLength(2)
    expect(selectionRemoves).toHaveLength(2)
  })
})
