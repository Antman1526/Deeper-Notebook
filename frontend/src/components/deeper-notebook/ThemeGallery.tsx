'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { RotateCcw, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { peekStoredTheme, writeStoredTheme } from '@/lib/theme-storage'
import {
  DEFAULT_THEME_ID,
  THEME_BY_ID,
  THEME_CATALOG,
  THEME_GROUPS,
  isThemeId,
  type ThemeId,
} from '@/lib/themes/catalog'

import { ThemePreviewCard } from './ThemePreviewCard'

interface ThemeBridge {
  setTheme?: (theme: string) => void
}

type ThemeWindow = Window & {
  DN?: ThemeBridge
  ONP?: ThemeBridge
}

function readActiveTheme(): ThemeId {
  try {
    const storedTheme = peekStoredTheme(localStorage)
    if (storedTheme && isThemeId(storedTheme)) return storedTheme
  } catch {
    // Storage may be disabled; the Research Core default remains available.
  }

  const documentTheme = document.documentElement.dataset.theme
  if (documentTheme && isThemeId(documentTheme)) return documentTheme

  return DEFAULT_THEME_ID
}

function setDocumentTheme(themeId: ThemeId) {
  const theme = THEME_BY_ID[themeId]
  document.documentElement.dataset.theme = themeId
  document.documentElement.classList.toggle('dark', theme.dark)
}

export function ThemeGallery() {
  const originalTheme = useRef<ThemeId>(DEFAULT_THEME_ID)
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>(DEFAULT_THEME_ID)
  const [previewingTheme, setPreviewingTheme] = useState<ThemeId | null>(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const activeTheme = readActiveTheme()
    originalTheme.current = activeTheme
    setSelectedTheme(activeTheme)
  }, [])

  const matchingThemes = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    if (!normalizedQuery) return THEME_CATALOG

    return THEME_CATALOG.filter(theme =>
      `${theme.label} ${theme.description}`.toLocaleLowerCase().includes(normalizedQuery),
    )
  }, [query])

  const handlePreview = (themeId: ThemeId) => {
    setDocumentTheme(themeId)
    setPreviewingTheme(themeId)
  }

  const handleRestore = () => {
    setDocumentTheme(originalTheme.current)
    setPreviewingTheme(null)
  }

  const handleApply = (themeId: ThemeId) => {
    setDocumentTheme(themeId)
    setSelectedTheme(themeId)
    setPreviewingTheme(null)

    try {
      writeStoredTheme(localStorage, themeId)
    } catch {
      // The native bridge can still persist when browser storage is disabled.
    }

    const themeBridge = (window as ThemeWindow).DN ?? (window as ThemeWindow).ONP
    themeBridge?.setTheme?.(themeId)
    originalTheme.current = themeId
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/25 p-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block flex-1">
          <span className="sr-only">Search themes</span>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search themes"
            aria-label="Search themes"
            className="bg-background pl-9"
          />
        </label>
        {previewingTheme && (
          <Button type="button" variant="outline" size="sm" onClick={handleRestore}>
            <RotateCcw aria-hidden="true" />
            Restore previous theme
          </Button>
        )}
      </div>

      <p className="sr-only" aria-live="polite">
        {previewingTheme
          ? `Previewing ${THEME_BY_ID[previewingTheme].label}. Apply it to save this theme or restore the previous theme.`
          : `${THEME_BY_ID[selectedTheme].label} is applied.`}
      </p>

      {matchingThemes.length === 0 && (
        <div className="rounded-lg border border-dashed px-4 py-10 text-center" role="status">
          <p className="text-sm font-medium">No themes match “{query.trim()}”.</p>
          <p className="mt-1 text-sm text-muted-foreground">Try a color, mood, or theme name.</p>
        </div>
      )}

      {THEME_GROUPS.map(group => {
        const themes = matchingThemes.filter(theme => theme.group === group.id)
        if (themes.length === 0) return null

        return (
          <section key={group.id} aria-labelledby={`theme-group-${group.id}`} className="space-y-3">
            <div className="flex items-baseline justify-between gap-3 border-b pb-2">
              <h3 id={`theme-group-${group.id}`} className="text-sm font-semibold tracking-tight">
                {group.label}
              </h3>
              <span className="text-xs tabular-nums text-muted-foreground">
                {themes.length} {themes.length === 1 ? 'theme' : 'themes'}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {themes.map(theme => (
                <ThemePreviewCard
                  key={theme.id}
                  theme={theme}
                  selected={selectedTheme === theme.id}
                  previewing={previewingTheme === theme.id}
                  onPreview={() => handlePreview(theme.id)}
                  onApply={() => handleApply(theme.id)}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
