import { zhCN, enUS, zhTW, ptBR, ja, fr, ru, bn, es, Locale } from 'date-fns/locale'

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
  'es-ES': es,
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
 * v0.7.189 — Format a Date as a localised "YYYY-MM-DD HH:MM:SS"
 * string using the app's i18n language, not the OS locale.
 *
 * `Date.prototype.toLocaleString()` (with no args) honours the
 * browser/OS locale, not the language the user picked in the app's
 * settings. Same component would render two different date formats
 * if one site used `formatDateTime(d, language)` and another used
 * bare `d.toLocaleString()`. This helper centralises the
 * `language → BCP-47 locale tag` mapping the LoginForm already
 * applied ad-hoc so every date-time render is consistent.
 *
 * Robust to:
 *   - null / undefined / empty-string input → returns ''
 *   - malformed date strings → returns the original string
 *     unchanged (lets the caller decide on a fallback)
 *
 * @param value - Date, ISO string, or anything `new Date()` accepts
 * @param language - The app's i18n language (e.g. 'zh-CN', 'en-US')
 * @returns Localised date-time string, or '' for invalid input
 */
export function formatDateTime(
  value: Date | string | null | undefined,
  language: string,
): string {
  if (value == null || value === '') return ''
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return typeof value === 'string' ? value : ''
  // Map our i18n codes to BCP-47 locale tags accepted by Intl.
  // Most map 1:1; only zh-* needs explicit mapping because the
  // tag is the same string.
  const locale = LOCALE_BCP47_MAP[language] || 'en-US'
  return d.toLocaleString(locale)
}

/**
 * v0.7.189 — Same as formatDateTime but date-only (no time
 * component). Useful for "last seen" / "due date" displays.
 */
export function formatDate(
  value: Date | string | null | undefined,
  language: string,
): string {
  if (value == null || value === '') return ''
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return typeof value === 'string' ? value : ''
  const locale = LOCALE_BCP47_MAP[language] || 'en-US'
  return d.toLocaleDateString(locale)
}

// BCP-47 mapping for Intl APIs. Our app uses the same tags as
// BCP-47 so this is mostly identity, but keeping it as a Map
// makes future divergences (e.g. fallback to a region-neutral
// tag) trivial.
const LOCALE_BCP47_MAP: Record<string, string> = {
  'zh-CN': 'zh-CN',
  'zh-TW': 'zh-TW',
  'en-US': 'en-US',
  'pt-BR': 'pt-BR',
  'ja-JP': 'ja-JP',
  'fr-FR': 'fr-FR',
  'ru-RU': 'ru-RU',
  'bn-IN': 'bn-IN',
  'es-ES': 'es-ES',
  'it-IT': 'it-IT',
}
