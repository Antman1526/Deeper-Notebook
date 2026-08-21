'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, RotateCcw, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  peekStoredTheme,
  readRecentThemeIds,
  recordRecentThemeId,
  THEME_SELECTION_CHANGE_EVENT,
  writeStoredTheme,
} from '@/lib/theme-storage'
import {
  applyCatalogTheme,
  resolveCatalogTheme,
  useThemeStore,
} from '@/lib/stores/theme-store'
import {
  DEFAULT_THEME_ID,
  THEME_BY_ID,
  THEME_CATALOG,
  THEME_GROUPS,
  isThemeId,
  type ThemeId,
} from '@/lib/themes/catalog'

import { ThemePreviewCard } from './ThemePreviewCard'

const RECOMMENDED_THEME_IDS = [
  'gemini-forward-light', 'gemini-forward-dark',
  'research-core-light', 'research-core-dark',
  'archive-paper', 'high-contrast-light', 'high-contrast-dark',
] as const

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
  const effectiveTheme = themeId === 'system'
    ? useThemeStore.getState().getSystemTheme()
    : 'light'
  applyCatalogTheme(document.documentElement, resolveCatalogTheme(themeId, effectiveTheme))
}

function readValidatedRecentThemeIds(): ThemeId[] {
  try {
    return readRecentThemeIds(localStorage).filter(isThemeId)
  } catch {
    return []
  }
}

export function ThemeGallery() {
  const originalTheme = useRef<ThemeId>(DEFAULT_THEME_ID)
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>(DEFAULT_THEME_ID)
  const [previewingTheme, setPreviewingTheme] = useState<ThemeId | null>(null)
  const [recentThemeIds, setRecentThemeIds] = useState<ThemeId[]>([])
  const [showMoreThemes, setShowMoreThemes] = useState(false)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const activeTheme = readActiveTheme()
    const nextRecentThemeIds = readValidatedRecentThemeIds()
    originalTheme.current = activeTheme
    setSelectedTheme(activeTheme)
    setRecentThemeIds(nextRecentThemeIds)
    if (!RECOMMENDED_THEME_IDS.some(themeId => themeId === activeTheme)) {
      setShowMoreThemes(true)
    }

    const handleCanonicalThemeChange = () => {
      const nextTheme = readActiveTheme()
      originalTheme.current = nextTheme
      setSelectedTheme(nextTheme)
      setRecentThemeIds(readValidatedRecentThemeIds())
      if (!RECOMMENDED_THEME_IDS.some(themeId => themeId === nextTheme)) {
        setShowMoreThemes(true)
      }
      setPreviewingTheme(null)
    }
    window.addEventListener(THEME_SELECTION_CHANGE_EVENT, handleCanonicalThemeChange)
    return () => window.removeEventListener(THEME_SELECTION_CHANGE_EVENT, handleCanonicalThemeChange)
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

    let didWriteStoredTheme = false
    try {
      writeStoredTheme(localStorage, themeId)
      didWriteStoredTheme = true
    } catch {
      // The native bridge can still persist when browser storage is disabled.
    }

    if (didWriteStoredTheme) {
      try {
        recordRecentThemeId(localStorage, themeId)
        setRecentThemeIds(readValidatedRecentThemeIds())
      } catch {
        // Recent history is best effort and must not block the canonical apply.
      }
    }

    const themeBridge = (window as ThemeWindow).DN ?? (window as ThemeWindow).ONP
    themeBridge?.setTheme?.(themeId)
    originalTheme.current = themeId
  }

  const hasSearch = query.trim().length > 0
  const recentThemes = recentThemeIds.map(themeId => THEME_BY_ID[themeId])
  const recentThemeIdSet = new Set(recentThemeIds)
  const recommendedThemes = RECOMMENDED_THEME_IDS.map(themeId => THEME_BY_ID[themeId])
  const moreThemes = THEME_CATALOG.filter(theme =>
    !recentThemeIdSet.has(theme.id)
      && !RECOMMENDED_THEME_IDS.some(themeId => themeId === theme.id),
  )

  const renderThemeSection = (
    sectionId: string,
    label: string,
    themes: readonly (typeof THEME_CATALOG[number])[],
  ) => {
    if (themes.length === 0) return null

    return (
      <section key={sectionId} aria-labelledby={`theme-section-${sectionId}`} className="space-y-3">
        <div className="flex items-baseline justify-between gap-3 border-b pb-2">
          <h3 id={`theme-section-${sectionId}`} className="text-sm font-semibold tracking-tight">
            {label}
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
              sectionLabel={sectionId === 'recent' ? label : undefined}
              onPreview={() => handlePreview(theme.id)}
              onApply={() => handleApply(theme.id)}
            />
          ))}
        </div>
      </section>
    )
  }

  const renderCatalogGroups = (themes: readonly (typeof THEME_CATALOG[number])[]) => (
    <div id="more-themes" className="space-y-6">
      {THEME_GROUPS.map(group => {
        const groupThemes = themes.filter(theme => theme.group === group.id)
        return renderThemeSection(group.id, group.label, groupThemes)
      })}
    </div>
  )

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

      {hasSearch
        ? renderCatalogGroups(matchingThemes)
        : (
          <>
            {renderThemeSection('recommended', 'Recommended', recommendedThemes)}
            {renderThemeSection('recent', 'Recent', recentThemes)}
            <div className="flex justify-center">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-expanded={showMoreThemes}
                aria-controls="more-themes"
                onClick={() => setShowMoreThemes(value => !value)}
              >
                {showMoreThemes ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
                {showMoreThemes ? 'Hide more themes' : 'Show more themes'}
              </Button>
            </div>
            {showMoreThemes && renderCatalogGroups(moreThemes)}
          </>
        )}
    </div>
  )
}
