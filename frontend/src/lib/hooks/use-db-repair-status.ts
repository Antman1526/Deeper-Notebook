// v0.8.67q — poll whether the launcher flagged the SurrealDB live-query state
// as corrupt (a worker crash that bricks source processing). Drives
// DbRepairBanner. Polls in the background so the banner appears within ~a
// minute of the crash, and clears itself once the user restarts (the next boot
// runs the backup-first auto-repair and clears the flag).
'use client'

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export const DB_REPAIR_QUERY_KEY = ['system', 'db-repair-needed'] as const

interface DbRepairStatus {
  needs_repair: boolean
}

export function useDbRepairStatus() {
  return useQuery<DbRepairStatus>({
    queryKey: DB_REPAIR_QUERY_KEY,
    // apiClient.baseURL already ends in `/api`, so the path is relative to it.
    queryFn: async () => {
      const { data } = await apiClient.get<DbRepairStatus>(
        '/system/db-repair-needed'
      )
      return data
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  })
}
