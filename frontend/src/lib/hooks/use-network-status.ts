// v0.8.68 — poll the backend's network state (offline probe + the user's
// Offline-mode toggle). Drives NetworkStatusBadge. Same shape as
// use-db-repair-status (v0.8.67q): TanStack Query polling against the
// system router.
'use client'

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export const NETWORK_STATUS_QUERY_KEY = ['system', 'network-status'] as const

export interface NetworkStatus {
  status: 'online' | 'offline' | 'unknown'
  forced_offline: boolean
  local_fallback_model: string | null
  checked_epoch_ms: number
}

export function useNetworkStatus() {
  return useQuery<NetworkStatus>({
    queryKey: NETWORK_STATUS_QUERY_KEY,
    // apiClient.baseURL already ends in `/api`, so the path is relative to it.
    queryFn: async () => {
      const { data } = await apiClient.get<NetworkStatus>(
        '/system/network-status'
      )
      return data
    },
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    retry: 1,
  })
}
