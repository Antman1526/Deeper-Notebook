'use client'

import { useEffect } from 'react'

import {
  isMotionPreference,
  isTransparencyPreference,
  isWallpaperPreference,
  useDisplayPreferencesStore,
  type DisplayPreferencesState,
  type MotionPreference,
  type TransparencyPreference,
  type WallpaperPreference,
} from '@/lib/stores/display-preferences-store'

type DisplayPreferenceValues = Pick<
  DisplayPreferencesState,
  'wallpaper' | 'motion' | 'transparency'
>

const WALLPAPER_OPTIONS: readonly { value: WallpaperPreference; label: string }[] = [
  { value: 'aurora', label: 'Aurora' },
  { value: 'static', label: 'Static' },
  { value: 'off', label: 'Off' },
]

const MOTION_OPTIONS: readonly { value: MotionPreference; label: string }[] = [
  { value: 'system', label: 'Follow system' },
  { value: 'full', label: 'Full motion' },
  { value: 'reduced', label: 'Reduced motion' },
]

const TRANSPARENCY_OPTIONS: readonly { value: TransparencyPreference; label: string }[] = [
  { value: 'frosted', label: 'Frosted' },
  { value: 'solid', label: 'Solid' },
]

function resolveMotionPreference(value: MotionPreference): 'system' | 'full' | 'reduced' {
  if (value === 'reduced') return 'reduced'

  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'reduced'
      : value
  } catch {
    return value
  }
}

/**
 * Keep the already-established root display contract in sync with a live
 * preference update. The store remains the only persistence authority; this
 * function only mirrors its allowlisted values into DOM attributes.
 */
export function applyDisplayPreferencesToDocument(values: DisplayPreferenceValues) {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  root.dataset.dnWallpaper = values.wallpaper
  root.dataset.dnMotion = resolveMotionPreference(values.motion)
  root.dataset.dnTransparency = values.transparency
}

export function DisplayPreferencesPanel() {
  const wallpaper = useDisplayPreferencesStore((state) => state.wallpaper)
  const motion = useDisplayPreferencesStore((state) => state.motion)
  const transparency = useDisplayPreferencesStore((state) => state.transparency)
  const setWallpaper = useDisplayPreferencesStore((state) => state.setWallpaper)
  const setMotion = useDisplayPreferencesStore((state) => state.setMotion)
  const setTransparency = useDisplayPreferencesStore((state) => state.setTransparency)

  useEffect(() => {
    applyDisplayPreferencesToDocument({ wallpaper, motion, transparency })
  }, [motion, transparency, wallpaper])

  const updateWallpaper = (value: string) => {
    if (!isWallpaperPreference(value)) return
    const next = { wallpaper: value, motion, transparency }
    setWallpaper(value)
    applyDisplayPreferencesToDocument(next)
  }

  const updateMotion = (value: string) => {
    if (!isMotionPreference(value)) return
    const next = { wallpaper, motion: value, transparency }
    setMotion(value)
    applyDisplayPreferencesToDocument(next)
  }

  const updateTransparency = (value: string) => {
    if (!isTransparencyPreference(value)) return
    const next = { wallpaper, motion, transparency: value }
    setTransparency(value)
    applyDisplayPreferencesToDocument(next)
  }

  return (
    <section aria-labelledby="display-preferences-heading" className="space-y-4 rounded-lg border bg-card/50 p-4">
      <div>
        <h2 id="display-preferences-heading" className="text-lg font-semibold">
          Display preferences
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Adjust the ambient folio presentation without changing your selected theme.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <label className="space-y-2 text-sm font-medium" htmlFor="display-wallpaper">
          <span>Wallpaper</span>
          <select
            id="display-wallpaper"
            value={wallpaper}
            onChange={(event) => updateWallpaper(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {WALLPAPER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm font-medium" htmlFor="display-motion">
          <span>Motion</span>
          <select
            id="display-motion"
            value={motion}
            onChange={(event) => updateMotion(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {MOTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm font-medium" htmlFor="display-transparency">
          <span>Transparency</span>
          <select
            id="display-transparency"
            value={transparency}
            onChange={(event) => updateTransparency(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {TRANSPARENCY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  )
}
