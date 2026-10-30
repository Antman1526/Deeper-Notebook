'use client'

import { useState, useEffect } from 'react'

/**
 * Hook to detect if viewport matches a media query.
 * Returns false during SSR to avoid hydration mismatches.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    setMatches(mediaQuery.matches)

    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches)
    }

    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [query])

  return matches
}

/**
 * Returns true if viewport is >= 1024px (Tailwind's 'lg' breakpoint)
 */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 1024px)')
}

/**
 * v0.8.130 — true at >= 1280px (Tailwind's 'xl'). The notebook workspace shows four
 * columns from here; between 1024 and 1279px Notes and Studio share a side panel.
 */
export function useIsWideDesktop(): boolean {
  return useMediaQuery('(min-width: 1280px)')
}
