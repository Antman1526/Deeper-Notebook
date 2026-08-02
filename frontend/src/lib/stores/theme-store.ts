import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { peekStoredTheme } from '@/lib/theme-storage'
import { DEFAULT_THEME_ID, THEME_BY_ID, isThemeId, type ThemeId } from '@/lib/themes/catalog'

export type Theme = 'light' | 'dark' | 'system'
export type EffectiveTheme = Exclude<Theme, 'system'>
export type CatalogThemeSource = 'catalog' | 'legacy'

export function normalizeCatalogTheme(
  value: string | null | undefined,
  effectiveTheme: EffectiveTheme,
  source: CatalogThemeSource = 'catalog',
): ThemeId | null {
  if (!value) return null
  if (value === 'light') return 'light-blue'
  if (source === 'legacy' && value === 'system') {
    return effectiveTheme === 'dark' ? 'dark' : 'light-blue'
  }
  return isThemeId(value) ? value : null
}

/**
 * Resolve a persisted catalog selection to the concrete palette that should
 * be painted. `system` is intentionally kept as a selection until this point
 * so the provider can own the single OS appearance listener.
 */
export function resolveCatalogTheme(
  selection: ThemeId,
  effectiveTheme: EffectiveTheme,
): ThemeId {
  if (selection === 'system') return effectiveTheme === 'dark' ? 'dark' : 'light-blue'
  return selection
}

/**
 * Read the canonical catalog selection without resolving `system`. This is
 * distinct from the effective palette and is what determines listener
 * ownership in ThemeProvider.
 */
export function getStoredCatalogSelection(): ThemeId | null {
  if (typeof window === 'undefined') return null

  try {
    return normalizeCatalogTheme(peekStoredTheme(localStorage), 'light')
  } catch {
    return null
  }
}

export function getStoredCatalogTheme(effectiveTheme: EffectiveTheme): ThemeId | null {
  const selection = getStoredCatalogSelection()
  return selection ? resolveCatalogTheme(selection, effectiveTheme) : null
}

interface ThemeState {
  theme: Theme
  legacyThemeOverride: boolean
  appliedTheme: EffectiveTheme
  setTheme: (theme: Theme) => void
  setAppliedTheme: (theme: EffectiveTheme) => void
  getSystemTheme: () => EffectiveTheme
  getEffectiveTheme: () => EffectiveTheme
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      legacyThemeOverride: false,
      appliedTheme: 'light',

      setAppliedTheme: (appliedTheme: EffectiveTheme) => set({ appliedTheme }),
      
      setTheme: (theme: Theme) => {
        set({ theme, legacyThemeOverride: true })
        
        if (typeof window !== 'undefined') {
          const effectiveTheme = theme === 'system' ? get().getSystemTheme() : theme
          const catalogTheme = normalizeCatalogTheme(theme, effectiveTheme, 'legacy')
            ?? DEFAULT_THEME_ID
          applyCatalogTheme(window.document.documentElement, catalogTheme)
        }
      },
      
      getSystemTheme: () => {
        if (typeof window !== 'undefined') {
          return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        }
        return 'light'
      },
      
      getEffectiveTheme: () => {
        const { theme } = get()
        return theme === 'system' ? get().getSystemTheme() : theme
      }
    }),
    {
      name: 'theme-storage',
      partialize: (state) => ({ theme: state.theme })
    }
  )
)

export function applyCatalogTheme(root: HTMLElement, theme: ThemeId) {
  root.setAttribute('data-theme', theme)
  root.classList.remove('light', 'dark')
  root.classList.toggle('dark', THEME_BY_ID[theme].dark)

  // Consumers read this provider/application-applied signal instead of
  // installing their own OS media-query listeners.
  if (typeof window !== 'undefined') {
    useThemeStore.getState().setAppliedTheme(THEME_BY_ID[theme].dark ? 'dark' : 'light')
  }
}

// Hook for components to use theme. `appliedTheme` starts at the SSR-safe
// light value and is updated whenever ThemeProvider or an application surface
// applies a concrete catalog palette. This hook intentionally has no OS
// media-query listener; ThemeProvider owns that single source of truth.
export function useTheme() {
  const theme = useThemeStore(state => state.theme)
  const setTheme = useThemeStore(state => state.setTheme)
  const effectiveTheme = useThemeStore(state => state.appliedTheme)

  return {
    theme,
    setTheme,
    effectiveTheme,
    isDark: effectiveTheme === 'dark',
  }
}
