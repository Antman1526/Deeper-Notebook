// v0.8.70 — in-app update notifier hooks.
// The check runs on mount with a 6h staleTime so reopening the app within the
// window doesn't re-ping GitHub (the backend also caches). The query is
// A failed check remains a query error; consumers render the safe unavailable
// state instead of exposing raw transport details or a download action.
'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { updatesApi, UpdateStatus } from '@/lib/api/updates'

export const UPDATES_QUERY_KEY = ['updates', 'check'] as const

const SIX_HOURS_MS = 6 * 60 * 60 * 1000

export function useUpdateCheck() {
  return useQuery<UpdateStatus>({
    queryKey: UPDATES_QUERY_KEY,
    queryFn: () => updatesApi.check(),
    staleTime: SIX_HOURS_MS,
    // The banner is a passive notice; don't re-fetch on every focus.
    refetchOnWindowFocus: false,
    retry: 1,
  })
}

export function useSkipVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (version: string) => updatesApi.skip(version),
    onSuccess: (data) => queryClient.setQueryData(UPDATES_QUERY_KEY, data),
  })
}

export function useSetUpdateEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => updatesApi.setEnabled(enabled),
    onSuccess: (data) => queryClient.setQueryData(UPDATES_QUERY_KEY, data),
  })
}

/** Force a fresh check (the Settings "Check now" button). */
export function useCheckForUpdatesNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => updatesApi.check(true),
    onSuccess: (data) => queryClient.setQueryData(UPDATES_QUERY_KEY, data),
  })
}
