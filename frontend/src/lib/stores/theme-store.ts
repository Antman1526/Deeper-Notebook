import { useEffect, useState } from 'react'
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

export function applyCatalogTheme(root: HTMLElement, theme: ThemeId) {
  root.setAttribute('data-theme', theme)
  root.classList.remove('light', 'dark')
  root.classList.toggle('dark', THEME_BY_ID[theme].dark)
}

interface ThemeState {
  theme: Theme
  legacyThemeOverride: boolean
  setTheme: (theme: Theme) => void
  getSystemTheme: () => EffectiveTheme
  getEffectiveTheme: () => EffectiveTheme
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      legacyThemeOverride: false,
      
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

// Hook for components to use theme
//
// v0.7.59 — compute effectiveTheme client-side only.
//
// The previous version called `getEffectiveTheme()` during render. On
// the server `typeof window === 'undefined'` so it returned 'light';
// on the client, after Zustand's persist middleware rehydrated, it
// could return 'dark' from localStorage. Any component that used
// `isDark` for class names hydration-mismatched on the first paint,
// flickering between the SSR default and the persisted choice.
//
// We now seed effectiveTheme as 'light' (matches SSR) and update it
// inside useEffect — that effect only runs client-side, AFTER React
// has committed the first render, so the SSR ↔ first-render output
// is identical. Subsequent renders pick up the real value.
//
// We also listen for the system-theme media query so `theme === 'system'`
// follows the OS dynamically without requiring a manual setTheme().
export function useTheme() {
  const { theme, setTheme, getEffectiveTheme, getSystemTheme } = useThemeStore()
  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    setEffectiveTheme(getEffectiveTheme())
    if (theme === 'system' && typeof window !== 'undefined') {
      const mql = window.matchMedia('(prefers-color-scheme: dark)')
      const onChange = () => setEffectiveTheme(getSystemTheme())
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    }
  }, [theme, getEffectiveTheme, getSystemTheme])

  return {
    theme,
    setTheme,
    effectiveTheme,
    isDark: effectiveTheme === 'dark',
  }
}
