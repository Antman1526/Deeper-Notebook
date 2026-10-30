import { resolveIntlLocale } from './date-locale'

/**
 * v0.8.130 — Format a number with the app's i18n language, not the OS
 * locale. A German UI on an English Mac must show "1.234,5", which bare
 * `toLocaleString()` / `toFixed()` cannot do.
 *
 * null / undefined → '' so callers can pass optional API fields directly.
 */
export function formatNumber(
  value: number | null | undefined,
  language: string,
  options?: Intl.NumberFormatOptions,
): string {
  if (value == null) return ''
  return new Intl.NumberFormat(resolveIntlLocale(language), options).format(value)
}

/**
 * v0.8.130 — Localised stand-in for `value.toFixed(digits)` when the
 * result is shown to the user: always exactly `digits` fraction digits.
 */
export function formatDecimal(
  value: number | null | undefined,
  language: string,
  digits: number,
): string {
  return formatNumber(value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}
