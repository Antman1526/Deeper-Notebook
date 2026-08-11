'use client'

import { useQuery } from '@tanstack/react-query'

import { runtimeApi, type RuntimeSnapshot } from '@/lib/api/runtime'

export const RUNTIME_SNAPSHOT_QUERY_KEY = ['runtime', 'snapshot'] as const
const RUNTIME_SNAPSHOT_STALE_TIME_MS = 30_000

/** Shared, read-only runtime snapshot query for Horizon and Settings. */
export function useRuntimeSnapshot(options: { enabled?: boolean } = {}) {
  return useQuery<RuntimeSnapshot>({
    queryKey: RUNTIME_SNAPSHOT_QUERY_KEY,
    queryFn: runtimeApi.getSnapshot,
    staleTime: RUNTIME_SNAPSHOT_STALE_TIME_MS,
    refetchOnWindowFocus: false,
    retry: false,
    enabled: options.enabled ?? true,
  })
}
