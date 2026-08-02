const CANONICAL_THEME_KEY = 'dn-theme'
const LEGACY_THEME_KEY = 'onp-theme'

export function peekStoredTheme(storage: Storage): string | null {
  return storage.getItem(CANONICAL_THEME_KEY) ?? storage.getItem(LEGACY_THEME_KEY)
}

export function readStoredTheme(storage: Storage): string | null {
  const canonical = storage.getItem(CANONICAL_THEME_KEY)
  if (canonical) return canonical

  const legacy = storage.getItem(LEGACY_THEME_KEY)
  if (legacy) storage.setItem(CANONICAL_THEME_KEY, legacy)
  return legacy
}

export function writeStoredTheme(storage: Storage, theme: string): void {
  storage.setItem(CANONICAL_THEME_KEY, theme)
  storage.setItem(LEGACY_THEME_KEY, theme)

  // ThemeProvider uses this same-tab signal to re-evaluate canonical
  // selection authority. The browser `storage` event only reaches other
  // documents, while ThemeSwitcher and ThemeGallery update this document.
  if (typeof window !== 'undefined' && storage === window.localStorage) {
    window.dispatchEvent(new Event('dn-theme-change'))
  }
}
