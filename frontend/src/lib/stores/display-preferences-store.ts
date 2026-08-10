import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type WallpaperPreference = 'aurora' | 'static' | 'off'
export type MotionPreference = 'system' | 'full' | 'reduced'
export type TransparencyPreference = 'frosted' | 'solid'

export interface DisplayPreferencesState {
  wallpaper: WallpaperPreference
  motion: MotionPreference
  transparency: TransparencyPreference
  setWallpaper(value: WallpaperPreference): void
  setMotion(value: MotionPreference): void
  setTransparency(value: TransparencyPreference): void
  reset(): void
}

export const DISPLAY_PREFERENCES_STORAGE_KEY = 'dn-display-preferences-v1'

export const DEFAULT_DISPLAY_PREFERENCES: Pick<
  DisplayPreferencesState,
  'wallpaper' | 'motion' | 'transparency'
> = {
  wallpaper: 'aurora',
  motion: 'system',
  transparency: 'frosted',
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

function readPersistedPreferences(value: unknown): Partial<typeof DEFAULT_DISPLAY_PREFERENCES> {
  if (!isRecord(value)) return {}

  return {
    wallpaper: isWallpaperPreference(value.wallpaper) ? value.wallpaper : undefined,
    motion: isMotionPreference(value.motion) ? value.motion : undefined,
    transparency: isTransparencyPreference(value.transparency) ? value.transparency : undefined,
  }
}

function safePreferences(state: Pick<DisplayPreferencesState, 'wallpaper' | 'motion' | 'transparency'>) {
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
