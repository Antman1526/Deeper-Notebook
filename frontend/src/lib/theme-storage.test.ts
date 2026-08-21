import { beforeEach, describe, expect, it } from 'vitest'

import { readRecentThemeIds, recordRecentThemeId } from './theme-storage'

const RECENTS_KEY = 'dn-theme-recents'

describe('theme recents storage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('records unique theme IDs newest first', () => {
    recordRecentThemeId(localStorage, 'archive-paper')
    recordRecentThemeId(localStorage, 'gemini-forward-dark')
    recordRecentThemeId(localStorage, 'archive-paper')

    expect(readRecentThemeIds(localStorage)).toEqual([
      'archive-paper',
      'gemini-forward-dark',
    ])
  })

  it('returns an empty list for malformed or non-array JSON', () => {
    localStorage.setItem(RECENTS_KEY, '{not-json')
    expect(readRecentThemeIds(localStorage)).toEqual([])

    localStorage.setItem(RECENTS_KEY, JSON.stringify({ theme: 'archive-paper' }))
    expect(readRecentThemeIds(localStorage)).toEqual([])
  })

  it('drops non-string entries while preserving string IDs', () => {
    localStorage.setItem(
      RECENTS_KEY,
      JSON.stringify(['archive-paper', 42, null, { id: 'dracula' }, 'dracula']),
    )

    expect(readRecentThemeIds(localStorage)).toEqual(['archive-paper', 'dracula'])
  })

  it('deduplicates existing entries and keeps at most four IDs', () => {
    localStorage.setItem(
      RECENTS_KEY,
      JSON.stringify(['archive-paper', 'dracula', 'archive-paper', 'nord', 'dark']),
    )

    recordRecentThemeId(localStorage, 'gemini-forward-dark')

    expect(readRecentThemeIds(localStorage)).toEqual([
      'gemini-forward-dark',
      'archive-paper',
      'dracula',
      'nord',
    ])
  })
})
