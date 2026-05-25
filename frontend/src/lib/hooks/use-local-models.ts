import { useQuery } from '@tanstack/react-query'
import apiClient from '@/lib/api/client'

export interface LocalModelHealth {
  name: string
  status: 'healthy' | 'unhealthy' | 'not_configured' | 'unknown'
  detail: string | null
  latency_ms: number | null
}

export interface LocalModelsHealthPayload {
  overall: 'healthy' | 'degraded' | 'down'
  models: LocalModelHealth[]
}

/**
 * Phase 1 — Poll the v0.8.0 backend `/api/local-models/health`
 * endpoint every 30 seconds + on window focus. Drives the
 * `LocalModelHealthBadges` component in the sidebar so users
 * see at a glance which local models are reachable.
 */
export function useLocalModelsHealth() {
  return useQuery<LocalModelsHealthPayload>({
    queryKey: ['local-models', 'health'],
    queryFn: async () => {
      const r = await apiClient.get('/local-models/health')
      return r.data
    },
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    // The endpoint is auth-exempted on the backend, so the
    // launcher splash can hit it pre-login. No retry on failure
    // since the badges go "unknown" gracefully if the call fails.
    retry: 1,
  })
}
