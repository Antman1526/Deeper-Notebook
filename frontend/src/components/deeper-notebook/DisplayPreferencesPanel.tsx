'use client'

import { useEffect } from 'react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  isMotionPreference,
  isTransparencyPreference,
  isWallpaperPreference,
  useDisplayPreferencesStore,
  type DisplayPreferencesState,
  type MotionPreference,
  type TransparencyPreference,
  type WallpaperPreference,
  isDensityPreference,
} from '@/lib/stores/display-preferences-store'

type DisplayPreferenceValues = Pick<
  DisplayPreferencesState,
  'wallpaper' | 'motion' | 'transparency' | 'density'
>

const WALLPAPER_OPTIONS: readonly { value: WallpaperPreference; labelKey: string }[] = [
  { value: 'aurora', labelKey: 'workspace.displayPreferencesPanel.wallpaperAurora' },
  { value: 'static', labelKey: 'workspace.displayPreferencesPanel.wallpaperStatic' },
  { value: 'off', labelKey: 'workspace.displayPreferencesPanel.wallpaperOff' },
]

const MOTION_OPTIONS: readonly { value: MotionPreference; labelKey: string }[] = [
  { value: 'system', labelKey: 'workspace.displayPreferencesPanel.motionSystem' },
  { value: 'full', labelKey: 'workspace.displayPreferencesPanel.motionFull' },
  { value: 'reduced', labelKey: 'workspace.displayPreferencesPanel.motionReduced' },
]

const TRANSPARENCY_OPTIONS: readonly { value: TransparencyPreference; labelKey: string }[] = [
  { value: 'frosted', labelKey: 'workspace.displayPreferencesPanel.transparencyFrosted' },
  { value: 'solid', labelKey: 'workspace.displayPreferencesPanel.transparencySolid' },
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
const DENSITY_OPTIONS = [
  { value: 'comfortable', labelKey: 'workspace.displayPreferencesPanel.densityComfortable' },
  { value: 'compact', labelKey: 'workspace.displayPreferencesPanel.densityCompact' },
] as const

export function applyDisplayPreferencesToDocument(values: DisplayPreferenceValues) {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  root.dataset.dnWallpaper = values.wallpaper
  root.dataset.dnMotion = resolveMotionPreference(values.motion)
  root.dataset.dnTransparency = values.transparency
  root.dataset.dnDensity = values.density
}

export function DisplayPreferencesPanel() {
  const { t } = useTranslation()
  const wallpaper = useDisplayPreferencesStore((state) => state.wallpaper)
  const motion = useDisplayPreferencesStore((state) => state.motion)
  const transparency = useDisplayPreferencesStore((state) => state.transparency)
  const density = useDisplayPreferencesStore((state) => state.density)
  const focusMode = useDisplayPreferencesStore((state) => state.focusMode)
  const setWallpaper = useDisplayPreferencesStore((state) => state.setWallpaper)
  const setMotion = useDisplayPreferencesStore((state) => state.setMotion)
  const setTransparency = useDisplayPreferencesStore((state) => state.setTransparency)
  const setDensity = useDisplayPreferencesStore((state) => state.setDensity)
  const setFocusMode = useDisplayPreferencesStore((state) => state.setFocusMode)

  useEffect(() => {
    applyDisplayPreferencesToDocument({ wallpaper, motion, transparency, density })
  }, [density, motion, transparency, wallpaper])

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.dataset.dnFocusMode = focusMode ? 'true' : 'false'
  }, [focusMode])

  const updateWallpaper = (value: string) => {
    if (!isWallpaperPreference(value)) return
    const next = { wallpaper: value, motion, transparency, density }
    setWallpaper(value)
    applyDisplayPreferencesToDocument(next)
  }

  const updateMotion = (value: string) => {
    if (!isMotionPreference(value)) return
    const next = { wallpaper, motion: value, transparency, density }
    setMotion(value)
    applyDisplayPreferencesToDocument(next)
  }

  const updateDensity = (value: string) => {
    if (!isDensityPreference(value)) return
    const next = { wallpaper, motion, transparency, density: value }
    setDensity(value)
    applyDisplayPreferencesToDocument(next)
  }

  const updateTransparency = (value: string) => {
    if (!isTransparencyPreference(value)) return
    const next = { wallpaper, motion, transparency: value, density }
    setTransparency(value)
    applyDisplayPreferencesToDocument(next)
  }

  return (
    <section aria-labelledby="display-preferences-heading" className="space-y-4 rounded-lg border bg-card/50 p-4">
      <div>
        <h2 id="display-preferences-heading" className="text-lg font-semibold">
          {t('workspace.displayPreferencesPanel.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t('workspace.displayPreferencesPanel.description')}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-2 text-sm font-medium" htmlFor="display-wallpaper">
          <span>{t('workspace.displayPreferencesPanel.wallpaper')}</span>
          <select
            id="display-wallpaper"
            value={wallpaper}
            onChange={(event) => updateWallpaper(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {WALLPAPER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm font-medium" htmlFor="display-motion">
          <span>{t('workspace.displayPreferencesPanel.motion')}</span>
          <select
            id="display-motion"
            value={motion}
            onChange={(event) => updateMotion(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {MOTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm font-medium" htmlFor="display-transparency">
          <span>{t('workspace.displayPreferencesPanel.transparency')}</span>
          <select
            id="display-transparency"
            value={transparency}
            onChange={(event) => updateTransparency(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {TRANSPARENCY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm font-medium" htmlFor="display-density">
          <span>{t('workspace.displayPreferencesPanel.density')}</span>
          <select
            id="display-density"
            value={density}
            onChange={(event) => updateDensity(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {DENSITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 bg-background/50 p-3">
        <div>
          <p className="text-sm font-medium">{t('workspace.displayPreferencesPanel.focusMode')}</p>
          <p className="text-sm text-muted-foreground">
            {t('workspace.displayPreferencesPanel.focusModeDescription')}
          </p>
        </div>
        <Button
          type="button"
          variant={focusMode ? 'secondary' : 'outline'}
          aria-pressed={focusMode}
          aria-label={focusMode ? t('workspace.displayPreferencesPanel.exitFocusMode') : t('workspace.displayPreferencesPanel.enterFocusMode')}
          className="motion-reduce:transition-none"
          onClick={() => setFocusMode(!focusMode)}
        >
          {focusMode ? t('workspace.displayPreferencesPanel.exitFocusMode') : t('workspace.displayPreferencesPanel.enterFocusMode')}
        </Button>
      </div>
    </section>
  )
}
