import {
  useMutation,
  useQueries,
  useQuery,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useDebounce } from 'use-debounce'

import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { searchApi } from '@/lib/api/search'
import { vaultApi, type VaultMount } from '@/lib/api/vault'
import type { SearchRequest, SearchResponse } from '@/lib/types/search'
import {
  buildKnowledgeCatalog,
  type KnowledgeCatalogCandidate,
} from '@/lib/commands/knowledge-command-catalog'
import { vaultKeys } from '@/lib/hooks/use-vault'

export interface KnowledgeIndexedSearchOptions {
  mode: 'exact' | 'text' | 'semantic'
  spaceIds: string[]
  authorityKinds: ('app_owned' | 'external_read_only')[]
  tags: string[]
}

const defaultSearchOptions: KnowledgeIndexedSearchOptions = {
  mode: 'text', spaceIds: [], authorityKinds: [], tags: [],
}

const searchRequest = (query: string, type: 'text' | 'vector', options: KnowledgeIndexedSearchOptions): SearchRequest => ({
  query,
  type,
  limit: 25,
  search_sources: false,
  search_notes: true,
  minimum_score: 0.3,
  match_mode: options.mode,
  space_ids: options.spaceIds,
  authority_kinds: options.authorityKinds,
  tags: options.tags,
})

/**
 * Query-shaped text-search state. Data is available only when `isCurrent` is
 * true, so a result for an earlier query cannot be rendered as the live query.
 */
export type KnowledgeIndexedTextSearch =
  | (UseQueryResult<SearchResponse, Error> & {
    isCurrent: true
    query: string
  })
  | (Omit<UseQueryResult<SearchResponse, Error>, 'data'> & {
    data: undefined
    isCurrent: false
    query: string
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

export function useKnowledgeIndexedSearch(query: string, enabled: boolean, options: KnowledgeIndexedSearchOptions = defaultSearchOptions) {
  const liveQuery = query.trim()
  const [input, setInput] = useState('')
  useEffect(() => {
    setInput(liveQuery)
  }, [liveQuery])
  const [debounced] = useDebounce(input, 250)
  const textQuery = useQuery({
    queryKey: ['knowledge-command-search', options.mode, debounced, options.spaceIds, options.authorityKinds, options.tags],
    queryFn: () => searchApi.search(searchRequest(debounced, 'text', options)),
    enabled: enabled && options.mode !== 'semantic' && debounced.length >= 2,
    staleTime: 10_000,
  })
  const text: KnowledgeIndexedTextSearch = liveQuery === debounced
    ? { ...textQuery, isCurrent: true, query: liveQuery }
    : { ...textQuery, data: undefined, isCurrent: false, query: liveQuery }
  const semantic = useMutation({
    mutationKey: ['knowledge-command-search', 'semantic', query, options.spaceIds, options.authorityKinds, options.tags],
    mutationFn: (value: string) =>
      searchApi.search(searchRequest(value.trim(), 'vector', options)),
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
