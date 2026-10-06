import { zhCN, enUS, zhTW, ptBR, ja, fr, ru, bn, ca, es, de, pl, tr, Locale } from 'date-fns/locale'

/**
 * Mapping of language codes to date-fns locales.
 * Add new languages here as needed.
 */
const LOCALE_MAP: Record<string, Locale> = {
  'zh-CN': zhCN,
  'zh-TW': zhTW,
  'en-US': enUS,
  'pt-BR': ptBR,
  'ja-JP': ja,
  'fr-FR': fr,
  'ru-RU': ru,
  'bn-IN': bn,
  'ca-ES': ca,
  'es-ES': es,
  'de-DE': de,
  'pl-PL': pl,
  'tr-TR': tr,
}

/**
 * Get the date-fns locale for a given language code.
 * Falls back to English (en-US) if the language is not found.
 *
 * @param language - The language code (e.g., 'zh-CN', 'en-US')
 * @returns The corresponding date-fns Locale object
 */
export function getDateLocale(language: string): Locale {
  return LOCALE_MAP[language] || enUS
}

/**
 * v0.8.130 — Resolve the app's i18n language to a BCP-47 tag for Intl.
 *
 * The old explicit map silently dropped de-DE, ca-ES, pl-PL and tr-TR to
 * en-US, so a German UI still rendered "3/7/2026". Every shipped app
 * language is already a valid BCP-47 tag, so trust it when `Intl` accepts
 * it and only fall back to en-US for empty or malformed input.
 */
// BCP-47 tag for each app language. v0.8.130 — the table had omitted de-DE, ca-ES,
// pl-PL and tr-TR, so those silently formatted as en-US; it now lists all 14, and any
// other valid tag is passed through.
const LOCALE_BCP47_MAP: Record<string, string> = {
  'en-US': 'en-US', 'zh-CN': 'zh-CN', 'zh-TW': 'zh-TW', 'pt-BR': 'pt-BR', 'ja-JP': 'ja-JP',
  'it-IT': 'it-IT', 'fr-FR': 'fr-FR', 'ru-RU': 'ru-RU', 'bn-IN': 'bn-IN', 'ca-ES': 'ca-ES',
  'es-ES': 'es-ES', 'de-DE': 'de-DE', 'pl-PL': 'pl-PL', 'tr-TR': 'tr-TR',
}

export function resolveIntlLocale(language: string | null | undefined): string {
  if (!language) return 'en-US'
  if (LOCALE_BCP47_MAP[language]) return LOCALE_BCP47_MAP[language]
  try {
    return Intl.getCanonicalLocales(language)[0] ?? 'en-US'
  } catch {
    return 'en-US'
  }
}

function toValidDate(value: Date | string | null | undefined): Date | string | null {
  if (value == null || value === '') return null
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return typeof value === 'string' ? value : null
  return d
}

/**
 * v0.7.189 — Format a Date as a localised date-time string using the
 * app's i18n language, not the OS locale.
 *
 * `Date.prototype.toLocaleString()` (with no args) honours the
 * browser/OS locale, not the language the user picked in the app's
 * settings. Same component would render two different date formats
 * if one site used `formatDateTime(d, language)` and another used
 * bare `d.toLocaleString()`. This helper centralises the
 * `language → BCP-47 locale tag` mapping so every date-time render is
 * consistent. v0.8.130 — accepts optional Intl options.
 *
 * Robust to:
 *   - null / undefined / empty-string input → returns ''
 *   - malformed date strings → returns the original string
 *     unchanged (lets the caller decide on a fallback)
 *
 * @param value - Date, ISO string, or anything `new Date()` accepts
 * @param language - The app's i18n language (e.g. 'zh-CN', 'en-US')
 * @param options - Optional Intl.DateTimeFormat options
 * @returns Localised date-time string, or '' for invalid input
 */
export function formatDateTime(
  value: Date | string | null | undefined,
  language: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = toValidDate(value)
  if (d == null) return ''
  if (typeof d === 'string') return d
  return d.toLocaleString(resolveIntlLocale(language), options)
}

/**
 * v0.7.189 — Same as formatDateTime but date-only (no time
 * component). Useful for "last seen" / "due date" displays.
 */
export function formatDate(
  value: Date | string | null | undefined,
  language: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = toValidDate(value)
  if (d == null) return ''
  if (typeof d === 'string') return d
  return d.toLocaleDateString(resolveIntlLocale(language), options)
}

/** v0.8.130 — Time-only counterpart of formatDate. */
export function formatTime(
  value: Date | string | null | undefined,
  language: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = toValidDate(value)
  if (d == null) return ''
  if (typeof d === 'string') return d
  return d.toLocaleTimeString(resolveIntlLocale(language), options)
}
