// v0.7.105 — TanStack Query hooks for the host filesystem endpoints used
// by the directory-picker. Listings are short-lived (filesystem can
// change underfoot), so we keep staleTime low.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { filesystemApi, FsListParams } from '@/lib/api/filesystem'
import { FsListFilter } from '@/lib/types/api'

const FS_KEYS = {
  home: ['fs', 'home'] as const,
  list: (path: string, only: FsListFilter, showHidden: boolean) =>
    ['fs', 'list', path, only, showHidden] as const,
}

export function useFsHome(enabled = true) {
  return useQuery({
    queryKey: FS_KEYS.home,
    queryFn: () => filesystemApi.home(),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

interface UseFsListOptions {
  showHidden?: boolean
  only?: FsListFilter
  enabled?: boolean
}

export function useFsList(path: string | null, options: UseFsListOptions = {}) {
  const only = options.only ?? 'all'
  const showHidden = options.showHidden ?? false
  return useQuery({
    queryKey: FS_KEYS.list(path ?? '', only, showHidden),
    queryFn: () =>
      filesystemApi.list({
        path: path as string,
        show_hidden: showHidden,
        only,
      } satisfies FsListParams),
    enabled: !!path && (options.enabled ?? true),
    staleTime: 15 * 1000,
    refetchOnWindowFocus: false,
    retry: 0,
  })
}

export function useFsMkdir() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => filesystemApi.mkdir({ path, parents: true }),
    onSuccess: () => {
      // Listings under the parent path may now be stale.
      queryClient.invalidateQueries({ queryKey: ['fs', 'list'] })
    },
  })
}
