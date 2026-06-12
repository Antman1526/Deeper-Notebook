/**
 * v0.7.29 — system-readiness hook for the dashboard landing page.
 *
 * Reads /readyz (added in v0.7.15) on a 30-second interval. The
 * endpoint returns 200 with `checks.*` keys or 503 with the same
 * shape when any dependency is down — either way we get a stable
 * shape to render.
 *
 * Used by the Command Center to show "all systems go" vs "DB
 * unreachable" without the user needing to grep logs.
 */
'use client'

import { useQuery } from '@tanstack/react-query'
import apiClient from '@/lib/api/client'

export interface ReadyzChecks {
  database: 'online' | 'offline' | 'unknown'
  database_error: string | null
  migrations_applied: boolean
  migrations_pending: boolean
  migrations_error: string | null
}

export interface ReadyzResponse {
  status: 'ready' | 'not_ready'
  checks: ReadyzChecks
}

export function useSystemStatus(intervalMs: number = 30_000) {
  return useQuery<ReadyzResponse>({
    queryKey: ['system', 'readyz'],
    queryFn: async () => {
      try {
        // axios throws on 5xx by default; we want to consume the
        // 503 body too, so accept any status < 600 manually.
        const res = await apiClient.get<ReadyzResponse>('/readyz', {
          validateStatus: (s) => s < 600,
        })
        return res.data
      } catch (err) {
        // Network error — synthesize a "not ready" response so the
        // UI doesn't show stale state.
        return {
          status: 'not_ready',
          checks: {
            database: 'unknown',
            database_error: (err as Error)?.message ?? 'API unreachable',
            migrations_applied: false,
            migrations_pending: false,
            migrations_error: null,
          },
        }
      }
    },
    refetchInterval: intervalMs,
    refetchOnWindowFocus: true,
    staleTime: 5_000,
    retry: 1,
  })
}
