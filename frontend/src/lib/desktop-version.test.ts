import { describe, expect, it } from 'vitest'

import { readDesktopVersion } from './desktop-version'

describe('readDesktopVersion compatibility', () => {
  it('reads the canonical bridge value', () => {
    expect(readDesktopVersion({ DEEPER_NOTEBOOK_VERSION: '1.2.3' })).toBe('1.2.3')
  })

  it('falls back to the legacy bridge value', () => {
    expect(readDesktopVersion({ ONP_VERSION: '0.9.0' })).toBe('0.9.0')
  })

  it('gives the canonical bridge deterministic precedence', () => {
    expect(
      readDesktopVersion({
        DEEPER_NOTEBOOK_VERSION: '1.2.3',
        ONP_VERSION: '0.9.0',
      }),
    ).toBe('1.2.3')
  })
})
