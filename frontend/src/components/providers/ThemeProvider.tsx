'use client'

import { useEffect } from 'react'
import { DEFAULT_THEME_ID, type ThemeId } from '@/lib/themes/catalog'
import {
  applyCatalogTheme,
  getStoredCatalogTheme,
  normalizeCatalogTheme,
  useThemeStore,
} from '@/lib/stores/theme-store'

interface ThemeProviderProps {
  children: React.ReactNode
}

type CatalogThemeSource = 'document' | 'storage' | 'effective'

function getCatalogTheme(
  root: HTMLElement,
  effectiveTheme: 'light' | 'dark',
  theme: 'light' | 'dark' | 'system',
  legacyThemeOverride: boolean,
): { theme: ThemeId; source: CatalogThemeSource } {
  if (legacyThemeOverride) {
    return {
      theme: normalizeCatalogTheme(theme, effectiveTheme, 'legacy') ?? DEFAULT_THEME_ID,
      source: 'effective',
    }
  }

  const storedTheme = getStoredCatalogTheme(effectiveTheme)
  if (storedTheme) return { theme: storedTheme, source: 'storage' }

  const documentTheme = root.dataset.theme
  if (documentTheme) {
    const catalogTheme = normalizeCatalogTheme(documentTheme, effectiveTheme)
    const legacySystemFallback = theme === 'system'
      && (catalogTheme === 'dark' || catalogTheme === 'light-blue')
    if (catalogTheme && !legacySystemFallback) return { theme: catalogTheme, source: 'document' }
  }

  return {
    theme: normalizeCatalogTheme(effectiveTheme, effectiveTheme, 'legacy') ?? DEFAULT_THEME_ID,
    source: 'effective',
  }
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { theme, legacyThemeOverride, getSystemTheme, getEffectiveTheme } = useThemeStore()

  useEffect(() => {
    const root = window.document.documentElement
    const effectiveTheme = getEffectiveTheme()
    const catalogTheme = getCatalogTheme(root, effectiveTheme, theme, legacyThemeOverride)

    // The pre-hydration script is the catalog-theme authority. Legacy values
    // are normalized to the catalog before they reach the document.
    applyCatalogTheme(root, catalogTheme.theme)

    if (catalogTheme.source !== 'effective') return

    // Preserve legacy system changes when catalog selection came from the
    // effective legacy store rather than pre-hydration document or storage.
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      
      const handleChange = () => {
        const newSystemTheme = getSystemTheme()
        applyCatalogTheme(
          root,
          (legacyThemeOverride ? null : getStoredCatalogTheme(newSystemTheme))
            ?? normalizeCatalogTheme('system', newSystemTheme, 'legacy')
            ?? DEFAULT_THEME_ID,
        )
      }

      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [theme, legacyThemeOverride, getSystemTheme, getEffectiveTheme])

  return <>{children}</>
}
