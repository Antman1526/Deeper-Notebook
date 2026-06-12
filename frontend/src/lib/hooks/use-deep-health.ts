// v0.7.117 — TanStack Query wrapper around /healthz/deep.
//
// Used by the Setup Wizard (full per-subsystem traffic-light view) and
// the dashboard SetupBanner (one-line nag while degraded). Refetches
// on window focus so a user who fixes a model in another tab sees the
// status flip green without manual polling. 30s stale time keeps the
// background refetch from spamming the API on a healthy install.

'use client'

import { useQuery } from '@tanstack/react-query'
import { healthApi, type DeepHealthResponse } from '@/lib/api/health'

export const DEEP_HEALTH_QUERY_KEY = ['system', 'healthz', 'deep'] as const

export function useDeepHealth() {
  return useQuery<DeepHealthResponse>({
    queryKey: DEEP_HEALTH_QUERY_KEY,
    queryFn: healthApi.getDeepHealth,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: 1,
  })
}
