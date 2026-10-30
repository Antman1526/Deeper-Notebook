import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DisplayPreferencesPanel } from './DisplayPreferencesPanel'
import {
  DEFAULT_DISPLAY_PREFERENCES,
  useDisplayPreferencesStore,
} from '@/lib/stores/display-preferences-store'

describe('DisplayPreferencesPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    useDisplayPreferencesStore.setState(DEFAULT_DISPLAY_PREFERENCES)
    document.documentElement.dataset.theme = 'archive-paper'
    document.documentElement.dataset.dnWallpaper = 'aurora'
    document.documentElement.dataset.dnMotion = 'system'
    document.documentElement.dataset.dnTransparency = 'frosted'
    vi.restoreAllMocks()
  })

  it('labels every control and exposes keyboard-operable native selects', () => {
    render(<DisplayPreferencesPanel />)

    for (const label of ['workspace.displayPreferencesPanel.wallpaper', 'workspace.displayPreferencesPanel.motion', 'workspace.displayPreferencesPanel.transparency']) {
      const control = screen.getByRole('combobox', { name: label })
      expect(control).toBeEnabled()
      expect(control.tagName).toBe('SELECT')
    }

    expect(screen.getByRole('heading', { name: 'workspace.displayPreferencesPanel.heading' })).toBeVisible()
  })

  it('updates root display attributes and persists without changing the selected theme', () => {
    render(<DisplayPreferencesPanel />)

    fireEvent.change(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.wallpaper' }), {
      target: { value: 'off' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.motion' }), {
      target: { value: 'reduced' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.transparency' }), {
      target: { value: 'solid' },
    })

    expect(document.documentElement.dataset.dnWallpaper).toBe('off')
    expect(document.documentElement.dataset.dnMotion).toBe('reduced')
    expect(document.documentElement.dataset.dnTransparency).toBe('solid')
    expect(document.documentElement.dataset.theme).toBe('archive-paper')
    expect(JSON.parse(localStorage.getItem('dn-display-preferences-v1') ?? '{}')).toMatchObject({
      state: { wallpaper: 'off', motion: 'reduced', transparency: 'solid' },
    })
  })

  it('does not open a dialog or make a network request while changing preferences', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<DisplayPreferencesPanel />)

    fireEvent.change(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.wallpaper' }), {
      target: { value: 'static' },
    })

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(document.querySelector('[aria-modal="true"]')).not.toBeInTheDocument()
  })

  it('reflects persisted preferences when it mounts', () => {
    localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({
        state: { wallpaper: 'static', motion: 'full', transparency: 'solid' },
        version: 0,
      }),
    )
    useDisplayPreferencesStore.persist.rehydrate()

    render(<DisplayPreferencesPanel />)

    expect(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.wallpaper' })).toHaveValue('static')
    expect(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.motion' })).toHaveValue('full')
    expect(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.transparency' })).toHaveValue('solid')
    expect(document.documentElement.dataset.dnWallpaper).toBe('static')
    expect(document.documentElement.dataset.dnMotion).toBe('full')
    expect(document.documentElement.dataset.dnTransparency).toBe('solid')
  })

  it('keeps the root motion attribute reduced when the OS requests reduced motion', () => {
    const previousMatchMedia = window.matchMedia
    window.matchMedia = vi.fn(() => ({ matches: true }) as MediaQueryList)

    try {
      render(<DisplayPreferencesPanel />)
      fireEvent.change(screen.getByRole('combobox', { name: 'workspace.displayPreferencesPanel.motion' }), {
        target: { value: 'full' },
      })

      expect(useDisplayPreferencesStore.getState().motion).toBe('full')
      expect(document.documentElement.dataset.dnMotion).toBe('reduced')
    } finally {
      window.matchMedia = previousMatchMedia
    }
  })

  it('exposes focus mode in display preferences with explicit pressed state', () => {
    render(<DisplayPreferencesPanel />)

    const focus = screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' })
    expect(focus).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(focus)

    expect(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.exitFocusMode' })).toHaveAttribute('aria-pressed', 'true')
    expect(JSON.parse(localStorage.getItem('dn-display-preferences-v1') ?? '{}')).toMatchObject({
      state: { focusMode: true },
    })
    expect(document.documentElement.dataset.theme).toBe('archive-paper')
  })
})

// v0.8.87 — density renders, applies, and stamps the document attribute.
describe('density control', () => {
  it('offers Comfortable and Compact and stamps data-dn-density', () => {
    render(<DisplayPreferencesPanel />)
    const select = screen.getByLabelText('workspace.displayPreferencesPanel.density') as HTMLSelectElement
    expect(select.value).toBe('comfortable')
    fireEvent.change(select, { target: { value: 'compact' } })
    expect(document.documentElement.dataset.dnDensity).toBe('compact')
    fireEvent.change(select, { target: { value: 'comfortable' } })
    expect(document.documentElement.dataset.dnDensity).toBe('comfortable')
  })
})
