'use client'

import { useEffect } from 'react'
import { peekStoredTheme } from '@/lib/theme-storage'
import { THEME_BY_ID, isThemeId, type ThemeId } from '@/lib/themes/catalog'
import { useThemeStore } from '@/lib/stores/theme-store'

interface ThemeProviderProps {
  children: React.ReactNode
}

function getCatalogTheme(root: HTMLElement): ThemeId | null {
  const documentTheme = root.dataset.theme
  if (documentTheme && isThemeId(documentTheme)) return documentTheme

  try {
    const storedTheme = peekStoredTheme(localStorage)
    if (storedTheme && isThemeId(storedTheme)) return storedTheme
  } catch {
    // Storage may be disabled; retain the legacy theme-store behavior below.
  }

  return null
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { theme, getSystemTheme, getEffectiveTheme } = useThemeStore()

  useEffect(() => {
    const root = window.document.documentElement
    const catalogTheme = getCatalogTheme(root)

    // The pre-hydration script is the catalog-theme authority. Preserve its
    // selected ID rather than overwriting it with the legacy light/dark store.
    if (catalogTheme) {
      root.setAttribute('data-theme', catalogTheme)
      root.classList.remove('light', 'dark')
      root.classList.toggle('dark', THEME_BY_ID[catalogTheme].dark)
      return
    }

    // Legacy light/dark/system behavior remains available when no catalog
    // selection was applied before hydration.
    const effectiveTheme = getEffectiveTheme()
    root.classList.remove('light', 'dark')
    root.classList.add(effectiveTheme)
    root.setAttribute('data-theme', effectiveTheme)

    // Listen for system theme changes when using system preference
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      
      const handleChange = () => {
        const newSystemTheme = getSystemTheme()
        root.classList.remove('light', 'dark')
        root.classList.add(newSystemTheme)
        root.setAttribute('data-theme', newSystemTheme)
      }

      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [theme, getSystemTheme, getEffectiveTheme])

  return <>{children}</>
}
