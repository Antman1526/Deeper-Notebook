import type { Page } from '@playwright/test'

import { installResearchWorkbenchMocks } from './research-workbench'
import type { ThemeId } from '@/lib/themes/catalog'
import type {
  MotionPreference,
  TransparencyPreference,
  WallpaperPreference,
} from '@/lib/stores/display-preferences-store'

export interface LuminousFolioFixtureOptions {
  theme: ThemeId
  wallpaper?: WallpaperPreference
  motion?: MotionPreference
  transparency?: TransparencyPreference
}

/**
 * Visual proof is deterministic: it has fixed research data, no guided-tip
 * overlay, a pinned theme, and explicit display preferences before hydration.
 */
export async function installLuminousFolioFixture(
  page: Page,
  {
    theme,
    wallpaper = 'static',
    motion = 'reduced',
    transparency = 'solid',
  }: LuminousFolioFixtureOptions,
): Promise<void> {
  await installResearchWorkbenchMocks(page)
  await page.context().addCookies([
    { name: 'wizard_completed', value: 'true', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  await page.addInitScript((settings) => {
    localStorage.setItem('dn-theme', settings.theme)
    localStorage.setItem('dn-guided-tips-v1', JSON.stringify({
      state: { enabled: false, completed: {} }, version: 0,
    }))
    localStorage.setItem('dn-display-preferences-v1', JSON.stringify({
      state: {
        wallpaper: settings.wallpaper,
        motion: settings.motion,
        transparency: settings.transparency,
      },
      version: 0,
    }))
  }, { theme, wallpaper, motion, transparency })
}
