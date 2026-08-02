'use client'

import { useEffect } from 'react'
import { peekStoredTheme } from '@/lib/theme-storage'
import { DEFAULT_THEME_ID, THEME_BY_ID, isThemeId, type ThemeId } from '@/lib/themes/catalog'
import { useThemeStore } from '@/lib/stores/theme-store'

interface ThemeProviderProps {
  children: React.ReactNode
}

type CatalogThemeSource = 'document' | 'storage' | 'effective'

function normalizeCatalogTheme(value: string, effectiveTheme: 'light' | 'dark'): ThemeId | null {
  if (isThemeId(value)) return value
  if (value === 'light') return 'light-blue'
  if (value === 'system') return effectiveTheme === 'dark' ? 'dark' : 'light-blue'
  return null
}

function getCatalogTheme(
  root: HTMLElement,
  effectiveTheme: 'light' | 'dark',
): { theme: ThemeId; source: CatalogThemeSource } {
  const documentTheme = root.dataset.theme
  if (documentTheme) {
    const catalogTheme = normalizeCatalogTheme(documentTheme, effectiveTheme)
    if (catalogTheme) return { theme: catalogTheme, source: 'document' }
  }

  try {
    const storedTheme = peekStoredTheme(localStorage)
    if (storedTheme) {
      const catalogTheme = normalizeCatalogTheme(storedTheme, effectiveTheme)
      if (catalogTheme) return { theme: catalogTheme, source: 'storage' }
    }
  } catch {
    // Storage may be disabled; the effective theme remains a catalog fallback.
  }

  return {
    theme: normalizeCatalogTheme(effectiveTheme, effectiveTheme) ?? DEFAULT_THEME_ID,
    source: 'effective',
  }
}

function applyCatalogTheme(root: HTMLElement, theme: ThemeId) {
  root.setAttribute('data-theme', theme)
  root.classList.remove('light', 'dark')
  root.classList.toggle('dark', THEME_BY_ID[theme].dark)
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { theme, getSystemTheme, getEffectiveTheme } = useThemeStore()

  useEffect(() => {
    const root = window.document.documentElement
    const effectiveTheme = getEffectiveTheme()
    const catalogTheme = getCatalogTheme(root, effectiveTheme)

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
        applyCatalogTheme(root, normalizeCatalogTheme(newSystemTheme, newSystemTheme) ?? DEFAULT_THEME_ID)
      }

      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [theme, getSystemTheme, getEffectiveTheme])

  return <>{children}</>
}
