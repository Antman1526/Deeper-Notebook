const CANONICAL_THEME_KEY = 'dn-theme'

export function readStoredTheme(storage: Storage): string | null {
  return storage.getItem(CANONICAL_THEME_KEY)
}

export function writeStoredTheme(storage: Storage, theme: string): void {
  storage.setItem(CANONICAL_THEME_KEY, theme)
}
