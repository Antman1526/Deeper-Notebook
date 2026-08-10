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

    for (const label of ['Wallpaper', 'Motion', 'Transparency']) {
      const control = screen.getByRole('combobox', { name: label })
      expect(control).toBeEnabled()
      expect(control.tagName).toBe('SELECT')
    }

    expect(screen.getByRole('heading', { name: 'Display preferences' })).toBeVisible()
  })

  it('updates root display attributes and persists without changing the selected theme', () => {
    render(<DisplayPreferencesPanel />)

    fireEvent.change(screen.getByRole('combobox', { name: 'Wallpaper' }), {
      target: { value: 'off' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'Motion' }), {
      target: { value: 'reduced' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'Transparency' }), {
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

    fireEvent.change(screen.getByRole('combobox', { name: 'Wallpaper' }), {
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

    expect(screen.getByRole('combobox', { name: 'Wallpaper' })).toHaveValue('static')
    expect(screen.getByRole('combobox', { name: 'Motion' })).toHaveValue('full')
    expect(screen.getByRole('combobox', { name: 'Transparency' })).toHaveValue('solid')
    expect(document.documentElement.dataset.dnWallpaper).toBe('static')
    expect(document.documentElement.dataset.dnMotion).toBe('full')
    expect(document.documentElement.dataset.dnTransparency).toBe('solid')
  })

  it('keeps the root motion attribute reduced when the OS requests reduced motion', () => {
    const previousMatchMedia = window.matchMedia
    window.matchMedia = vi.fn(() => ({ matches: true }) as MediaQueryList)

    try {
      render(<DisplayPreferencesPanel />)
      fireEvent.change(screen.getByRole('combobox', { name: 'Motion' }), {
        target: { value: 'full' },
      })

      expect(useDisplayPreferencesStore.getState().motion).toBe('full')
      expect(document.documentElement.dataset.dnMotion).toBe('reduced')
    } finally {
      window.matchMedia = previousMatchMedia
    }
  })
})
