import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDateTime,
  formatTime,
  resolveIntlLocale,
} from './date-locale'

// Noon UTC so the calendar day is stable in every runner timezone.
const SAMPLE = new Date(Date.UTC(2026, 2, 7, 12, 0, 0))

describe('resolveIntlLocale', () => {
  it('passes through any valid app language, including ones missing from the old map', () => {
    expect(resolveIntlLocale('de-DE')).toBe('de-DE')
    expect(resolveIntlLocale('tr-TR')).toBe('tr-TR')
  })

  it('falls back to en-US for invalid input', () => {
    expect(resolveIntlLocale('')).toBe('en-US')
    expect(resolveIntlLocale('###')).toBe('en-US')
  })
})

describe('formatDate', () => {
  it('formats in German for de-DE', () => {
    expect(formatDate(SAMPLE, 'de-DE')).toBe('7.3.2026')
  })

  it('formats in US English for en-US', () => {
    expect(formatDate(SAMPLE, 'en-US')).toBe('3/7/2026')
  })

  it('accepts ISO strings and Intl options', () => {
    expect(
      formatDate(SAMPLE.toISOString(), 'de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }),
    ).toBe('07.03.2026')
    expect(formatDate(SAMPLE, 'en-US', { month: 'short', day: 'numeric', year: 'numeric' })).toBe(
      'Mar 7, 2026',
    )
  })

  it('returns "" for empty input and the raw string for unparsable input', () => {
    expect(formatDate(null, 'de-DE')).toBe('')
    expect(formatDate('', 'de-DE')).toBe('')
    expect(formatDate('garbage', 'de-DE')).toBe('garbage')
  })
})

describe('formatTime', () => {
  it('uses a 24h clock for de-DE and a 12h clock for en-US', () => {
    const opts = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' } as const
    expect(formatTime(SAMPLE, 'de-DE', opts)).toBe('12:00')
    expect(formatTime(SAMPLE, 'en-US', opts)).toBe('12:00 PM')
  })

  it('returns "" for empty input', () => {
    expect(formatTime(undefined, 'en-US')).toBe('')
  })
})

describe('formatDateTime', () => {
  it('honours de-DE instead of falling back to en-US', () => {
    expect(formatDateTime(SAMPLE, 'de-DE', { timeZone: 'UTC' })).toBe('7.3.2026, 12:00:00')
    expect(formatDateTime(SAMPLE, 'en-US', { timeZone: 'UTC' })).toBe('3/7/2026, 12:00:00 PM')
  })
})
