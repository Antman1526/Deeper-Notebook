'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

// v0.8.130 — the browser tab title names the current route in the UI language
// ("Notizbücher · Deeper Notebook"). Next.js route metadata is rendered on the server
// in English, so the titles are set here from the same keys the navigation uses.
const PRODUCT = 'Deeper Notebook'

export const ROUTE_TITLE_KEYS: Readonly<Record<string, string>> = {
  '/notebooks': 'navigation.notebooks',
  '/sources': 'navigation.sources',
  '/capture': 'navigation.appSidebar.capture',
  '/knowledge': 'navigation.knowledge',
  '/search': 'navigation.askAndSearch',
  '/studio': 'navigation.appSidebar.studio',
  '/podcasts': 'navigation.podcasts',
  '/podcasts/studio': 'podcasts.podcastStudio.title',
  '/study': 'navigation.study',
  '/transformations': 'navigation.transformations',
  '/settings': 'navigation.settings',
  '/settings/api-keys': 'navigation.models',
  '/settings/local-models': 'workspace.systemRouteFrames.titleLocalModels',
  '/settings/mcp': 'settings.mcp.navTitle',
  '/settings/launcher-prefs': 'settings.launcherPrefs.navTitle',
  '/advanced': 'navigation.advanced',
  '/setup-wizard': 'workspace.systemRouteFrames.titleSetup',
}

/** The most specific route prefix with a title (/settings/mcp before /settings). */
export function routeTitleKey(pathname: string | null): string | null {
  if (!pathname) return null
  let match: string | null = null
  for (const route of Object.keys(ROUTE_TITLE_KEYS)) {
    if ((pathname === route || pathname.startsWith(`${route}/`)) && (!match || route.length > match.length)) {
      match = route
    }
  }
  return match ? ROUTE_TITLE_KEYS[match] : null
}

export function DocumentTitle() {
  const pathname = usePathname()
  const { t, language } = useTranslation()
  const key = routeTitleKey(pathname)

  useEffect(() => {
    const title = key ? `${t(key)} · ${PRODUCT}` : PRODUCT
    const apply = () => {
      if (document.title !== title) document.title = title
    }
    apply()
    // Next.js commits the root layout's <title> after this effect on a fresh load, which
    // would put the bare brand back; keep the route title whenever the head changes.
    const observer = new MutationObserver(apply)
    observer.observe(document.head, { subtree: true, childList: true, characterData: true })
    return () => observer.disconnect()
  }, [key, t, language])

  return null
}
