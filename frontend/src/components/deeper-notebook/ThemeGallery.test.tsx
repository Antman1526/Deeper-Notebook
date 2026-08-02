import { fireEvent, render, screen } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeGallery } from './ThemeGallery'

type ThemeBridge = { setTheme: ReturnType<typeof vi.fn> }
type ThemeWindow = Window & { DN?: ThemeBridge; ONP?: ThemeBridge }

describe('ThemeGallery', () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = 'research-core-dark'
    document.documentElement.classList.add('dark')
  })

  afterEach(() => {
    delete (window as ThemeWindow).DN
    delete (window as ThemeWindow).ONP
    document.documentElement.dataset.theme = ''
    document.documentElement.classList.remove('dark')
    localStorage.clear()
  })

  it('renders the categorized catalog and filters by theme copy', () => {
    render(<ThemeGallery />)

    expect(screen.getByRole('heading', { name: 'Featured', level: 3 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Light', level: 3 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Dark', level: 3 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Accessibility', level: 3 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Classics', level: 3 })).toBeVisible()
    expect(screen.getByRole('button', { name: /Preview Research Core Light/ })).toBeVisible()
    expect(screen.getByText('High Contrast Dark')).toBeVisible()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search themes' }), {
      target: { value: 'archival' },
    })

    expect(screen.getByText('Archive Paper')).toBeVisible()
    expect(screen.queryByText('High Contrast Dark')).not.toBeInTheDocument()
  })

  it('supports a server render before browser globals are available', () => {
    vi.stubGlobal('document', undefined)

    try {
      expect(() => renderToString(<ThemeGallery />)).not.toThrow()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('keeps preview and restore DOM-only while Apply persists canonically', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical
    localStorage.setItem('dn-theme', 'research-core-dark')

    render(<ThemeGallery />)

    fireEvent.click(screen.getByRole('button', { name: /Preview Archive Paper/ }))
    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(canonical.setTheme).not.toHaveBeenCalled()
    expect(localStorage.getItem('dn-theme')).toBe('research-core-dark')

    fireEvent.click(screen.getByRole('button', { name: 'Restore previous theme' }))
    expect(document.documentElement.dataset.theme).toBe('research-core-dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(canonical.setTheme).not.toHaveBeenCalled()
    expect(localStorage.getItem('dn-theme')).toBe('research-core-dark')

    fireEvent.click(screen.getByRole('button', { name: 'Apply Archive Paper' }))
    expect(canonical.setTheme).toHaveBeenCalledWith('archive-paper')
    expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
  })
})
