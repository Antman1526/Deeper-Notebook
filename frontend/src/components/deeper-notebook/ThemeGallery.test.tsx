import { fireEvent, render, screen, within } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeGallery } from './ThemeGallery'

// Keys come back unchanged; interpolated values are appended so per-theme
// accessible names ("apply Archive Paper") stay distinguishable.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${Object.values(opts).join(' ')}` : key,
  }),
}))

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

  it('curates the initial gallery and discloses the remaining catalog on demand', () => {
    render(<ThemeGallery />)

    expect(screen.getByRole('heading', { name: 'workspace.themeGallery.recommended' })).toBeVisible()
    expect(screen.getByText('Archive Paper')).toBeVisible()
    expect(screen.queryByText('Dracula')).not.toBeInTheDocument()
    const moreThemesButton = screen.getByRole('button', { name: 'workspace.themeGallery.showMoreThemes' })
    expect(moreThemesButton).toBeVisible()
    expect(moreThemesButton).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(moreThemesButton)

    expect(screen.getByText('Dracula')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'workspace.catalog2.groupClassics' })).toBeVisible()
    expect(moreThemesButton).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows Recent after Apply and bypasses disclosure while searching', () => {
    render(<ThemeGallery />)

    fireEvent.click(screen.getByRole('button', { name: 'workspace.themeGallery.showMoreThemes' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Dracula' }))

    expect(screen.getByRole('heading', { name: 'workspace.themeGallery.recent' })).toBeVisible()
    expect(localStorage.getItem('dn-theme-recents')).toBe(JSON.stringify(['dracula']))

    fireEvent.change(screen.getByRole('searchbox', { name: 'workspace.themeGallery.searchThemes' }), {
      target: { value: 'nord' },
    })

    expect(screen.getByText('Nord')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'workspace.themeGallery.showMoreThemes' })).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('searchbox', { name: 'workspace.themeGallery.searchThemes' }), {
      target: { value: 'archivepaper' },
    })
    expect(screen.getByText('Archive Paper')).toBeVisible()
    expect(screen.queryByText('workspace.catalog2.themeNameHighContrastDark')).not.toBeInTheDocument()
  })

  it('keeps every recommended theme visible after applying a recommended theme', () => {
    render(<ThemeGallery />)

    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Archive Paper' }))

    const recommendedSection = screen.getByRole('heading', { name: 'workspace.themeGallery.recommended' }).closest('section')
    const recentSection = screen.getByRole('heading', { name: 'workspace.themeGallery.recent' }).closest('section')
    expect(recommendedSection).not.toBeNull()
    expect(recentSection).not.toBeNull()

    for (const label of [
      'Gemini-Forward Light',
      'Gemini-Forward Dark',
      'Research Core Light',
      'Research Core Dark',
      'Archive Paper',
      'workspace.catalog2.themeNameHighContrastLight',
      'workspace.catalog2.themeNameHighContrastDark',
    ]) {
      expect(within(recommendedSection!).getByText(label)).toBeVisible()
    }
    expect(within(recommendedSection!).getByRole('article', { name: 'workspace.themePreviewCard.articleLabel Archive Paper' })).toBeVisible()
    expect(within(recentSection!).getByText('Archive Paper')).toBeVisible()
    expect(within(recentSection!).getByRole('article', { name: 'workspace.themePreviewCard.articleLabelWithSection workspace.themeGallery.recent Archive Paper' })).toBeVisible()
  })

  it('writes canonical theme storage before recording an applied recent theme', () => {
    render(<ThemeGallery />)
    const setItemSpy = vi.spyOn(window.localStorage, 'setItem')

    try {
      fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Archive Paper' }))

      const writtenKeys = setItemSpy.mock.calls.map(([key]) => key)
      const legacyThemeStorageKey = ['onp', 'theme'].join('-')
      expect(writtenKeys).toContain('dn-theme')
      expect(writtenKeys).toContain(legacyThemeStorageKey)
      expect(writtenKeys).toContain('dn-theme-recents')
      expect(writtenKeys.indexOf('dn-theme')).toBeLessThan(writtenKeys.indexOf(legacyThemeStorageKey))
      expect(writtenKeys.indexOf(legacyThemeStorageKey)).toBeLessThan(writtenKeys.indexOf('dn-theme-recents'))
    } finally {
      setItemSpy.mockRestore()
    }
  })

  it('does not record recents when canonical theme storage fails', () => {
    localStorage.setItem('dn-theme-recents', JSON.stringify(['dracula']))
    render(<ThemeGallery />)

    const setItemSpy = vi.spyOn(window.localStorage, 'setItem').mockImplementation((key: string) => {
      if (key === 'dn-theme') {
        throw new DOMException('Quota exceeded', 'QuotaExceededError')
      }
    })
    setItemSpy.mockClear()

    try {
      fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Archive Paper' }))

      const writtenKeys = setItemSpy.mock.calls.map(([key]) => key)
      expect(writtenKeys).toContain('dn-theme')
      expect(writtenKeys).not.toContain('dn-theme-recents')
      expect(localStorage.getItem('dn-theme-recents')).toBe(JSON.stringify(['dracula']))
    } finally {
      setItemSpy.mockRestore()
    }
  })

  it('shows only catalog-valid persisted recents', () => {
    localStorage.setItem('dn-theme-recents', JSON.stringify(['not-a-theme', 'dracula']))

    render(<ThemeGallery />)

    expect(screen.getByRole('heading', { name: 'workspace.themeGallery.recent' })).toBeVisible()
    expect(screen.getByText('Dracula')).toBeVisible()
    expect(screen.queryByText('not-a-theme')).not.toBeInTheDocument()
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

    fireEvent.click(screen.getByRole('button', { name: /workspace\.themePreviewCard\.previewLabel Archive Paper/ }))
    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(canonical.setTheme).not.toHaveBeenCalled()
    expect(localStorage.getItem('dn-theme')).toBe('research-core-dark')
    expect(localStorage.getItem('dn-theme-recents')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'workspace.themeGallery.restorePrevious' }))
    expect(document.documentElement.dataset.theme).toBe('research-core-dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(canonical.setTheme).not.toHaveBeenCalled()
    expect(localStorage.getItem('dn-theme')).toBe('research-core-dark')
    expect(localStorage.getItem('dn-theme-recents')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Archive Paper' }))
    expect(canonical.setTheme).toHaveBeenCalledWith('archive-paper')
    expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
  })

  it('resolves System preview and restore through the current dark OS palette', () => {
    const previousMatchMedia = window.matchMedia
    window.matchMedia = vi.fn(() => ({ matches: true }) as MediaQueryList)

    try {
      localStorage.setItem('dn-theme', 'system')
      document.documentElement.dataset.theme = 'light-blue'
      document.documentElement.classList.remove('dark')

      render(<ThemeGallery />)

      fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.previewLabel workspace.catalog2.themeNameSystem' }))
      expect(document.documentElement.dataset.theme).toBe('dark')
      expect(document.documentElement).toHaveClass('dark')

      fireEvent.click(screen.getByRole('button', { name: 'workspace.themeGallery.restorePrevious' }))
      expect(document.documentElement.dataset.theme).toBe('dark')
      expect(document.documentElement).toHaveClass('dark')
    } finally {
      window.matchMedia = previousMatchMedia
    }
  })

  it('does not migrate legacy storage while mounting, previewing, or restoring', () => {
    document.documentElement.dataset.theme = ''
    document.documentElement.classList.remove('dark')
    localStorage.setItem('onp-theme', 'research-core-dark')

    render(<ThemeGallery />)

    expect(localStorage.getItem('dn-theme')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.previewLabel Archive Paper' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.themeGallery.restorePrevious' }))

    expect(document.documentElement.dataset.theme).toBe('research-core-dark')
    expect(localStorage.getItem('dn-theme')).toBeNull()
    expect(localStorage.getItem('onp-theme')).toBe('research-core-dark')
  })

  it('updates the restore baseline after Apply', () => {
    const canonical = { setTheme: vi.fn() }
    ;(window as ThemeWindow).DN = canonical

    render(<ThemeGallery />)

    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.applyLabel Archive Paper' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.themePreviewCard.previewLabel Research Core Light' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.themeGallery.restorePrevious' }))

    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(document.documentElement).not.toHaveClass('dark')
    const archivePaperCards = [
      screen.getByRole('article', { name: 'workspace.themePreviewCard.articleLabel Archive Paper' }),
      screen.getByRole('article', { name: 'workspace.themePreviewCard.articleLabelWithSection workspace.themeGallery.recent Archive Paper' }),
    ]
    for (const card of archivePaperCards) {
      expect(card).toHaveTextContent('workspace.themePreviewCard.current')
    }
    expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
    expect(canonical.setTheme).toHaveBeenCalledTimes(1)
    expect(canonical.setTheme).toHaveBeenCalledWith('archive-paper')
  })
})
