import {
  useMutation,
  useQueries,
  useQuery,
} from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useDebounce } from 'use-debounce'

import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { searchApi } from '@/lib/api/search'
import { vaultApi, type VaultMount } from '@/lib/api/vault'
import {
  buildKnowledgeCatalog,
  type KnowledgeCatalogCandidate,
} from '@/lib/commands/knowledge-command-catalog'
import { vaultKeys } from '@/lib/hooks/use-vault'

const searchRequest = (query: string, type: 'text' | 'vector') => ({
  query,
  type,
  limit: 25,
  search_sources: false,
  search_notes: true,
  minimum_score: 0.3,
})

export function useKnowledgeCatalog(
  mounts: VaultMount[],
  openTabs: readonly OpenKnowledgeTab[],
  enabled: boolean,
): {
  candidates: KnowledgeCatalogCandidate[]
  isLoading: boolean
  failedVaultCount: number
  retryFailedVaults: () => Promise<void>
} {
  const ready = mounts.filter(mount => mount.state === 'ready-read-only')
  const queries = useQueries({
    queries: ready.map(mount => ({
      queryKey: vaultKeys.files(mount.id),
      queryFn: () => vaultApi.files(mount.id),
      enabled,
      staleTime: 30_000,
    })),
  })
  const filesByVault = useMemo(() => new Map(
    ready.flatMap((mount, index) => queries[index]?.data
      ? [[mount.id, queries[index].data] as const]
      : []),
  ), [queries, ready])
  return {
    candidates: buildKnowledgeCatalog(ready, filesByVault, openTabs),
    isLoading: queries.some(query => query.isLoading),
    failedVaultCount: queries.filter(query => query.isError).length,
    retryFailedVaults: async () => {
      await Promise.all(
        queries.filter(query => query.isError).map(query => query.refetch()),
      )
    },
  }
}

export function useKnowledgeIndexedSearch(query: string, enabled: boolean) {
  const [input, setInput] = useState('')
  useEffect(() => {
    setInput(query.trim())
  }, [query])
  const [debounced] = useDebounce(input, 250)
  const text = useQuery({
    queryKey: ['knowledge-command-search', 'text', debounced],
    queryFn: () => searchApi.search(searchRequest(debounced, 'text')),
    enabled: enabled && debounced.length >= 2,
    staleTime: 10_000,
  })
  const semantic = useMutation({
    mutationFn: (value: string) =>
      searchApi.search(searchRequest(value.trim(), 'vector')),
  })
  return {
    text,
    semantic,
    runSemanticSearch: () => {
      const value = query.trim()
      if (value.length >= 2) semantic.mutate(value)
    },
  }
}
