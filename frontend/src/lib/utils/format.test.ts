import { describe, expect, it } from 'vitest'
import { formatDecimal, formatNumber } from './format'

describe('formatNumber', () => {
  it('uses German separators for de-DE', () => {
    expect(formatNumber(1234.5, 'de-DE')).toBe('1.234,5')
  })

  it('uses English separators for en-US', () => {
    expect(formatNumber(1234.5, 'en-US')).toBe('1,234.5')
  })

  it('falls back to en-US for an unknown language tag', () => {
    expect(formatNumber(1234.5, 'not a locale')).toBe('1,234.5')
    expect(formatNumber(1234.5, '')).toBe('1,234.5')
  })

  it('returns an empty string for null / undefined', () => {
    expect(formatNumber(null, 'de-DE')).toBe('')
    expect(formatNumber(undefined, 'en-US')).toBe('')
  })

  it('forwards Intl options', () => {
    expect(
      formatNumber(3, 'de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    ).toBe('3,0')
  })
})

describe('formatDecimal', () => {
  it('pads and rounds to a fixed number of digits like toFixed, but localised', () => {
    expect(formatDecimal(1234.56, 'de-DE', 1)).toBe('1.234,6')
    expect(formatDecimal(1234.56, 'en-US', 1)).toBe('1,234.6')
    expect(formatDecimal(2, 'de-DE', 2)).toBe('2,00')
    expect(formatDecimal(0.5, 'en-US', 0)).toBe('1')
  })

  it('returns an empty string for null / undefined', () => {
    expect(formatDecimal(null, 'de-DE', 1)).toBe('')
  })
})
