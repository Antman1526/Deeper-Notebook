/**
 * ThemeSwitcher — replaces upstream's <ThemeToggle> with a list of all 9
 * ONP themes. Live-switching via window.ONP.setTheme (defined by the
 * desktop wrapper's theme-injection JS in desktop/window.py).
 *
 * Shadow-layer component — see components/onp/README.md.
 *
 * Live-switch flow:
 *   1. User clicks a theme in the dropdown
 *   2. window.ONP.setTheme(theme) sets <html data-theme="..."> immediately
 *      (instant visual feedback — no reload)
 *   3. window.ONP.setTheme also POSTs to /api/onp/theme to persist to
 *      ~/.open-notebook-plus/config.toml
 *   4. Next page load: desktop/window.py re-reads config.toml, bakes in
 *      the new theme, injection JS applies it
 */
'use client'

import { useEffect, useState } from 'react'

import { onpFetch } from '@/lib/api/onp'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Palette, Check } from 'lucide-react'

// Kept in lockstep with desktop/window.py:_THEMES and api/routers/onp.py
const ONP_THEMES = [
  { id: 'light-blue', label: 'Light Blue', dark: false, swatch: '#FFFFFF' },
  { id: 'system', label: 'System', dark: false, swatch: '#FFFFFF' },
  { id: 'solarized-light', label: 'Solarized Light', dark: false, swatch: '#FDF6E3' },
  { id: 'github-light', label: 'GitHub Light', dark: false, swatch: '#FFFFFF' },
  { id: 'paper', label: 'Paper', dark: false, swatch: '#FBF8F1' },
  { id: 'dark', label: 'Dark', dark: true, swatch: '#0F1419' },
  { id: 'solarized-dark', label: 'Solarized Dark', dark: true, swatch: '#002B36' },
  { id: 'dracula', label: 'Dracula', dark: true, swatch: '#282A36' },
  { id: 'nord', label: 'Nord', dark: true, swatch: '#2E3440' },
]

interface OnpWindow {
  ONP?: {
    setTheme?: (theme: string) => void
    themes?: string[]
  }
}

interface ThemeSwitcherProps {
  iconOnly?: boolean
}

export function ThemeSwitcher({ iconOnly = false }: ThemeSwitcherProps) {
  const [activeTheme, setActiveTheme] = useState<string>('light-blue')

  // Read the current theme from <html data-theme="..."> on mount.
  // window.ONP.setTheme has already set that attribute by the time React
  // mounts — fallback to localStorage (preserves user choice across hard
  // reloads that may briefly race the injection), then to the API.
  useEffect(() => {
    const current = document.documentElement.dataset.theme
    if (current) {
      setActiveTheme(current)
      return
    }
    // v0.5.9 — localStorage fallback so the dropdown doesn't flicker to
    // the default while waiting for the API response.
    try {
      const cached = localStorage.getItem('onp-theme')
      if (cached) {
        setActiveTheme(cached)
        return
      }
    } catch {
      /* localStorage disabled — fall through to API */
    }
    onpFetch('/api/onp/theme')
      .then((r) => r.json())
      .then((d) => setActiveTheme(d.theme || 'light-blue'))
      .catch(() => {})
  }, [])

  const handleSelect = (themeId: string) => {
    setActiveTheme(themeId)
    // v0.5.9 — also write localStorage so a subsequent navigation that races
    // the injection still shows the right swatch in the dropdown.
    try { localStorage.setItem('onp-theme', themeId) } catch { /* noop */ }
    const w = window as OnpWindow & Window
    if (w.ONP?.setTheme) {
      w.ONP.setTheme(themeId)
    } else {
      onpFetch('/api/onp/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: themeId }),
      }).catch(() => {})
    }
  }

  const lightThemes = ONP_THEMES.filter((t) => !t.dark)
  const darkThemes = ONP_THEMES.filter((t) => t.dark)

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
      <DropdownMenuContent align="end" className="min-w-[180px]">
        {lightThemes.map((t) => (
          <DropdownMenuItem
            key={t.id}
            onClick={() => handleSelect(t.id)}
            className="gap-2"
          >
            <span
              className="inline-block h-3 w-3 rounded-full border"
              style={{ background: t.swatch, borderColor: 'var(--border)' }}
            />
            <span className="flex-1">{t.label}</span>
            {activeTheme === t.id && <Check className="h-3 w-3" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        {darkThemes.map((t) => (
          <DropdownMenuItem
            key={t.id}
            onClick={() => handleSelect(t.id)}
            className="gap-2"
          >
            <span
              className="inline-block h-3 w-3 rounded-full border"
              style={{ background: t.swatch, borderColor: '#444' }}
            />
            <span className="flex-1">{t.label}</span>
            {activeTheme === t.id && <Check className="h-3 w-3" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
