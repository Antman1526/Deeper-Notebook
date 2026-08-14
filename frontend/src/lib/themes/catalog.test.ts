import { describe, expect, it } from 'vitest'

import {
  DARK_THEME_IDS,
  DEFAULT_THEME_ID,
  getFreshThemeDefault,
  LEGACY_DEFAULT_THEME_ID,
  THEME_BY_ID,
  THEME_CATALOG,
  THEME_GROUPS,
  VISUAL_SYSTEM_DEFAULT_THEME_ID,
  isThemeId,
} from './catalog'

const expectedIds = [
  'research-core-dark', 'gemini-forward-light', 'research-core-light',
  'deep-ocean', 'graphite-lab', 'arctic-research', 'archive-paper',
  'high-contrast-dark', 'high-contrast-light',
  'light-blue', 'system', 'solarized-light', 'github-light', 'paper',
  'catppuccin-latte', 'rose-pine-dawn',
  'dark', 'midnight-aurora', 'tokyo-night', 'catppuccin-mocha',
  'rose-pine', 'one-dark', 'gruvbox-dark', 'solarized-dark', 'dracula', 'nord',
] as const

describe('Research Core OS theme catalog', () => {
  it('contains the exact 26 unique IDs and the approved fresh defaults', () => {
    expect(THEME_CATALOG.map(theme => theme.id)).toEqual(expectedIds)
    expect(THEME_CATALOG).toHaveLength(26)
    expect(new Set(THEME_CATALOG.map(theme => theme.id)).size).toBe(26)
    expect(DEFAULT_THEME_ID).toBe('research-core-dark')
    expect(LEGACY_DEFAULT_THEME_ID).toBe('research-core-dark')
    expect(VISUAL_SYSTEM_DEFAULT_THEME_ID).toBe('gemini-forward-light')
    expect(getFreshThemeDefault(false)).toBe('research-core-dark')
    expect(getFreshThemeDefault(true)).toBe('gemini-forward-light')
  })

  it('puts Gemini-forward light first among featured light themes', () => {
    expect(THEME_BY_ID['gemini-forward-light']).toMatchObject({ group: 'featured', dark: false })
    expect(THEME_CATALOG.find(theme => theme.group === 'featured' && !theme.dark)?.id)
      .toBe('gemini-forward-light')
  })

  it('marks the flagship and accessibility themes explicitly', () => {
    expect(THEME_BY_ID['research-core-dark'].group).toBe('featured')
    expect(THEME_BY_ID['research-core-light'].group).toBe('featured')
    expect(THEME_BY_ID['high-contrast-dark'].group).toBe('accessibility')
    expect(THEME_BY_ID['high-contrast-light'].group).toBe('accessibility')
  })

  it('exposes dark-mode and runtime guards', () => {
    expect(DARK_THEME_IDS).toContain('research-core-dark')
    expect(DARK_THEME_IDS).not.toContain('research-core-light')
    expect(isThemeId('archive-paper')).toBe(true)
    expect(isThemeId('unknown-neon')).toBe(false)
  })

  it('exports the one approved theme group order', () => {
    expect(THEME_GROUPS).toEqual([
      { id: 'featured', label: 'Featured' },
      { id: 'light', label: 'Light' },
      { id: 'dark', label: 'Dark' },
      { id: 'accessibility', label: 'Accessibility' },
      { id: 'classics', label: 'Classics' },
    ])
  })
})
