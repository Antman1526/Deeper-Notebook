/**
 * ThemeSwitcher — replaces upstream's <ThemeToggle> with a list of all
 * Deeper Notebook themes. Live-switching via window.DN.setTheme (defined by the
 * desktop wrapper's theme-injection JS in desktop/window.py).
 *
 * Shadow-layer component — see components/deeper-notebook/README.md.
 *
 * Live-switch flow:
 *   1. User clicks a theme in the dropdown
 *   2. window.DN.setTheme(theme) sets <html data-theme="..."> immediately
 *      (instant visual feedback — no reload)
 *   3. window.DN.setTheme also POSTs to the canonical theme endpoint
 *      ~/.deeper-notebook/config.toml
 *   4. Next page load: desktop/window.py re-reads config.toml, bakes in
 *      the new theme, injection JS applies it
 */
'use client'

import { useEffect, useState } from 'react'

import { deeperNotebookFetch } from '@/lib/api/deeper-notebook'
import { readStoredTheme, writeStoredTheme } from '@/lib/theme-storage'
import {
  DEFAULT_THEME_ID,
  THEME_CATALOG,
  isThemeId,
  type ThemeGroup,
  type ThemeId,
} from '@/lib/themes/catalog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Palette, Check } from 'lucide-react'

const THEME_GROUPS: readonly { id: ThemeGroup; label: string }[] = [
  { id: 'featured', label: 'Featured' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'accessibility', label: 'Accessibility' },
  { id: 'classics', label: 'Classics' },
]

interface ThemeBridge {
  setTheme?: (theme: string) => void
  themes?: string[]
}

interface DeeperNotebookWindow {
  DN?: ThemeBridge
  // Transitional fallback for existing desktop wrappers.
  ONP?: ThemeBridge
}

interface ThemeSwitcherProps {
  iconOnly?: boolean
}

export function ThemeSwitcher({ iconOnly = false }: ThemeSwitcherProps) {
  const [activeTheme, setActiveTheme] = useState<ThemeId>(DEFAULT_THEME_ID)

  // Read the current theme from <html data-theme="..."> on mount.
  // window.DN.setTheme has already set that attribute by the time React
  // mounts — fallback to localStorage (preserves user choice across hard
  // reloads that may briefly race the injection), then to the API.
  useEffect(() => {
    const current = document.documentElement.dataset.theme
    if (current && isThemeId(current)) {
      setActiveTheme(current)
      return
    }
    // v0.5.9 — localStorage fallback so the dropdown doesn't flicker to
    // the default while waiting for the API response.
    try {
      const cached = readStoredTheme(localStorage)
      if (cached && isThemeId(cached)) {
        setActiveTheme(cached)
        return
      }
    } catch {
      /* localStorage disabled — fall through to API */
    }
    deeperNotebookFetch('/api/deeper-notebook/theme')
      .then((r) => r.json())
      .then((data) => setActiveTheme(isThemeId(data.theme) ? data.theme : DEFAULT_THEME_ID))
      .catch(() => {})
  }, [])

  const handleSelect = (themeId: ThemeId) => {
    setActiveTheme(themeId)
    // v0.5.9 — also write localStorage so a subsequent navigation that races
    // the injection still shows the right swatch in the dropdown.
    try { writeStoredTheme(localStorage, themeId) } catch { /* noop */ }
    const w = window as DeeperNotebookWindow & Window
    const themeBridge = w.DN ?? w.ONP
    if (themeBridge?.setTheme) {
      themeBridge.setTheme(themeId)
    } else {
      deeperNotebookFetch('/api/deeper-notebook/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: themeId }),
      }).catch(() => {})
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={iconOnly ? 'ghost' : 'outline'}
          size={iconOnly ? 'icon' : 'default'}
          className={
            iconOnly
              ? 'h-9 w-full sidebar-menu-item'
              : 'w-full justify-start gap-2 sidebar-menu-item'
          }
        >
          <Palette className="h-[1.2rem] w-[1.2rem]" aria-hidden="true" />
          {!iconOnly && <span>Theme</span>}
          <span className="sr-only">Switch theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[min(32rem,var(--radix-dropdown-menu-content-available-height))] min-w-56">
        {THEME_GROUPS.map((group, groupIndex) => {
          const themes = THEME_CATALOG.filter(theme => theme.group === group.id)

          return (
            <div key={group.id}>
              {groupIndex > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {group.label}
              </DropdownMenuLabel>
              {themes.map(theme => (
                <DropdownMenuItem
                  key={theme.id}
                  onClick={() => handleSelect(theme.id)}
                  className="gap-2"
                >
                  <span
                    className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
                    style={{
                      background: theme.preview.canvas,
                      borderColor: theme.preview.border,
                    }}
                    aria-hidden="true"
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: theme.preview.primary }}
                    />
                  </span>
                  <span className="flex-1">{theme.label}</span>
                  {activeTheme === theme.id && <Check className="h-3 w-3" aria-hidden="true" />}
                </DropdownMenuItem>
              ))}
            </div>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
