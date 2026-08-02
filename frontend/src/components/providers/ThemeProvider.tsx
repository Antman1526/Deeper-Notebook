'use client'

import { useEffect, useState } from 'react'
import { DEFAULT_THEME_ID, type ThemeId } from '@/lib/themes/catalog'
import { THEME_SELECTION_CHANGE_EVENT } from '@/lib/theme-storage'
import {
  applyCatalogTheme,
  getStoredCatalogSelection,
  normalizeCatalogTheme,
  resolveCatalogTheme,
  useThemeStore,
} from '@/lib/stores/theme-store'

interface ThemeProviderProps {
  children: React.ReactNode
}

type CatalogThemeSource = 'document' | 'storage' | 'effective'

interface CatalogThemeResolution {
  selection: ThemeId
  theme: ThemeId
  source: CatalogThemeSource
}

function getCatalogTheme(
  root: HTMLElement,
  effectiveTheme: 'light' | 'dark',
  systemTheme: 'light' | 'dark',
  theme: 'light' | 'dark' | 'system',
  legacyThemeOverride: boolean,
): CatalogThemeResolution {
  if (legacyThemeOverride) {
    const selection = theme === 'system'
      ? 'system'
      : normalizeCatalogTheme(theme, effectiveTheme, 'legacy') ?? DEFAULT_THEME_ID
    return {
      selection,
      theme: resolveCatalogTheme(selection, selection === 'system' ? systemTheme : effectiveTheme),
      source: 'effective',
    }
  }

  const storedSelection = getStoredCatalogSelection()
  if (storedSelection) {
    return {
      selection: storedSelection,
      theme: resolveCatalogTheme(storedSelection, storedSelection === 'system' ? systemTheme : effectiveTheme),
      source: 'storage',
    }
  }

  const documentTheme = root.dataset.theme
  if (documentTheme) {
    const catalogTheme = normalizeCatalogTheme(documentTheme, effectiveTheme)
    const legacySystemFallback = theme === 'system'
      && (catalogTheme === 'dark' || catalogTheme === 'light-blue')
    if (catalogTheme && !legacySystemFallback) {
      return {
        selection: catalogTheme,
        theme: resolveCatalogTheme(catalogTheme, catalogTheme === 'system' ? systemTheme : effectiveTheme),
        source: 'document',
      }
    }
  }

  const selection = theme === 'system'
    ? 'system'
    : normalizeCatalogTheme(theme, effectiveTheme, 'legacy') ?? DEFAULT_THEME_ID
  return {
    selection,
    theme: resolveCatalogTheme(selection, selection === 'system' ? systemTheme : effectiveTheme),
    source: 'effective',
  }
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { theme, legacyThemeOverride, getSystemTheme, getEffectiveTheme } = useThemeStore()
  const [storageRevision, setStorageRevision] = useState(0)

  useEffect(() => {
    const handleCanonicalThemeChange = () => setStorageRevision(revision => revision + 1)
    window.addEventListener(THEME_SELECTION_CHANGE_EVENT, handleCanonicalThemeChange)
    return () => window.removeEventListener(THEME_SELECTION_CHANGE_EVENT, handleCanonicalThemeChange)
  }, [])

  useEffect(() => {
    const root = window.document.documentElement
    const effectiveTheme = getEffectiveTheme()
    const systemTheme = getSystemTheme()
    const catalogTheme = getCatalogTheme(root, effectiveTheme, systemTheme, theme, legacyThemeOverride)

    // The pre-hydration script is the catalog-theme authority. Legacy values
    // are normalized to the catalog before they reach the document.
    applyCatalogTheme(root, catalogTheme.theme)

    // `system` is a persisted selection, not a palette. The provider owns the
    // one OS media-query listener for both canonical storage and legacy store
    // fallbacks, while explicit catalog IDs remain fixed across OS changes.
    if (catalogTheme.selection === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

      const handleChange = (event: MediaQueryListEvent) => {
        const newSystemTheme = typeof event.matches === 'boolean'
          ? (event.matches ? 'dark' : 'light')
          : getSystemTheme()
        applyCatalogTheme(root, resolveCatalogTheme('system', newSystemTheme))
      }

      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [theme, legacyThemeOverride, getSystemTheme, getEffectiveTheme, storageRevision])

  return <>{children}</>
}
