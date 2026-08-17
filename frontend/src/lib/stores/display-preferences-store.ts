import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type WallpaperPreference = 'aurora' | 'static' | 'off'
export type MotionPreference = 'system' | 'full' | 'reduced'
export type TransparencyPreference = 'frosted' | 'solid'
// v0.8.87 — Phase 2B density. Owner picked Comfortable as the default; Compact
// tightens workspace spacing for dense screens.
export type DensityPreference = 'comfortable' | 'compact'

export interface DisplayPreferencesState {
  wallpaper: WallpaperPreference
  motion: MotionPreference
  transparency: TransparencyPreference
  density: DensityPreference
  focusMode: boolean
  setWallpaper(value: WallpaperPreference): void
  setMotion(value: MotionPreference): void
  setTransparency(value: TransparencyPreference): void
  setDensity(value: DensityPreference): void
  setFocusMode(value: boolean): void
  toggleFocusMode(): void
  reset(): void
}

export const DISPLAY_PREFERENCES_STORAGE_KEY = 'dn-display-preferences-v1'

export const DEFAULT_DISPLAY_PREFERENCES: Pick<
  DisplayPreferencesState,
  'wallpaper' | 'motion' | 'transparency' | 'density' | 'focusMode'
> = {
  wallpaper: 'aurora',
  motion: 'system',
  transparency: 'frosted',
  density: 'comfortable',
  focusMode: false,
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function isWallpaperPreference(value: unknown): value is WallpaperPreference {
  return value === 'aurora' || value === 'static' || value === 'off'
}

export function isMotionPreference(value: unknown): value is MotionPreference {
  return value === 'system' || value === 'full' || value === 'reduced'
}

export function isTransparencyPreference(value: unknown): value is TransparencyPreference {
  return value === 'frosted' || value === 'solid'
}

export function isDensityPreference(value: unknown): value is DensityPreference {
  return value === 'comfortable' || value === 'compact'
}

function readPersistedPreferences(value: unknown): Partial<typeof DEFAULT_DISPLAY_PREFERENCES> {
  if (!isRecord(value)) return {}

  return {
    wallpaper: isWallpaperPreference(value.wallpaper) ? value.wallpaper : undefined,
    motion: isMotionPreference(value.motion) ? value.motion : undefined,
    transparency: isTransparencyPreference(value.transparency) ? value.transparency : undefined,
    density: isDensityPreference(value.density) ? value.density : undefined,
    focusMode: typeof value.focusMode === 'boolean' ? value.focusMode : undefined,
  }
}

function safePreferences(state: Pick<DisplayPreferencesState, 'wallpaper' | 'motion' | 'transparency' | 'density' | 'focusMode'>) {
  return {
    wallpaper: isWallpaperPreference(state.wallpaper)
      ? state.wallpaper
      : DEFAULT_DISPLAY_PREFERENCES.wallpaper,
    motion: isMotionPreference(state.motion)
      ? state.motion
      : DEFAULT_DISPLAY_PREFERENCES.motion,
    transparency: isTransparencyPreference(state.transparency)
      ? state.transparency
      : DEFAULT_DISPLAY_PREFERENCES.transparency,
    density: isDensityPreference(state.density)
      ? state.density
      : DEFAULT_DISPLAY_PREFERENCES.density,
    focusMode: typeof state.focusMode === 'boolean'
      ? state.focusMode
      : DEFAULT_DISPLAY_PREFERENCES.focusMode,
  }
}

export const useDisplayPreferencesStore = create<DisplayPreferencesState>()(
  persist(
    (set) => ({
      ...DEFAULT_DISPLAY_PREFERENCES,
      setWallpaper: (value) => set({
        wallpaper: isWallpaperPreference(value)
          ? value
          : DEFAULT_DISPLAY_PREFERENCES.wallpaper,
      }),
      setMotion: (value) => set({
        motion: isMotionPreference(value)
          ? value
          : DEFAULT_DISPLAY_PREFERENCES.motion,
      }),
      setTransparency: (value) => set({
        transparency: isTransparencyPreference(value)
          ? value
          : DEFAULT_DISPLAY_PREFERENCES.transparency,
      }),
      setDensity: (value) => set({
        density: isDensityPreference(value)
          ? value
          : DEFAULT_DISPLAY_PREFERENCES.density,
      }),
      setFocusMode: (value) => set({
        focusMode: typeof value === 'boolean'
          ? value
          : DEFAULT_DISPLAY_PREFERENCES.focusMode,
      }),
      toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),
      reset: () => set(DEFAULT_DISPLAY_PREFERENCES),
    }),
    {
      name: DISPLAY_PREFERENCES_STORAGE_KEY,
      partialize: (state) => safePreferences(state),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...safePreferences({
          ...currentState,
          ...readPersistedPreferences(persistedState),
        }),
      }),
    },
  ),
)
