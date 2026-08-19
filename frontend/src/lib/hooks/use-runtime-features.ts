'use client'

import { useEffect } from 'react'

import apiClient from '@/lib/api/client'
import { applyRuntimeFeatures } from '@/lib/features'

/**
 * v0.8.107 — adopt backend-authoritative feature state once per session.
 *
 * Frontend flags are `NEXT_PUBLIC_*`, which Next INLINES at build time, so a
 * packaged .app has its UI feature set frozen in the bundle. Turning a feature
 * off server-side left its controls rendered and dead, because the client never
 * learned the backend had stopped supporting it (§4.3 of PROJECT-DEEP-DIVE —
 * the dead Refresh/Remove buttons in the source gallery came from this).
 *
 * Deliberately fail-soft and silent. The inlined value is the default, so an
 * unreachable endpoint, a backend predating /api/features, or a malformed
 * payload all leave behaviour exactly as it is today. This hook can only ever
 * CORRECT a flag; it can never strand the UI, which is why it does not surface
 * an error state or block render.
 */
export function useRuntimeFeatures(): void {
  useEffect(() => {
    let cancelled = false

    void (async () => {
      try {
        const response = await apiClient.get<{ features?: unknown }>('/features')
        if (!cancelled) applyRuntimeFeatures(response.data?.features)
      } catch {
        // Intentionally silent: see the note above. A feature check that shouts
        // on a rolled-back or offline backend is worse than a stale flag.
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])
}
