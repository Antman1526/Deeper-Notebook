import { useMutation, useQuery, useQueryClient, type MutateOptions } from '@tanstack/react-query'

import { sourceVisualsApi } from '@/lib/api/source-visuals'
import { QUERY_KEYS, shouldRetryMutation } from '@/lib/api/query-client'
import { sourcesApi } from '@/lib/api/sources'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useSourceVisualsEnabled } from '@/lib/features-client'
import type { SourceVisualJob } from '@/lib/types/source-visuals'

type VisualMutationVariables = { sourceId: string; requestId: string }

function requestId(): string {
  return crypto.randomUUID()
}

function useSourceVisualMutation(operation: 'refresh' | 'remove') {
  const client = useQueryClient()
  const mutation = useMutation<SourceVisualJob, unknown, VisualMutationVariables>({
    mutationFn: ({ sourceId, requestId: stableRequestId }) =>
      sourceVisualsApi[operation](sourceId, stableRequestId),
    retry: shouldRetryMutation,
    onSuccess: async (_result, { sourceId }) => {
      await Promise.all([
        client.invalidateQueries({ predicate: query => query.queryKey[0] === 'sources' && (query.queryKey[1] === 'list' || query.queryKey[1] === 'infinite' || (query.queryKey[1] === 'visual' && query.queryKey[2] === 'recent')) }),
        client.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId), exact: true }),
        client.invalidateQueries({ queryKey: QUERY_KEYS.sourceVisual(sourceId), exact: true }),
        client.invalidateQueries({ queryKey: QUERY_KEYS.searchSources, exact: true }),
        client.invalidateQueries({ predicate: query => query.queryKey[0] === QUERY_KEYS.knowledgeSourceSearch[0] }),
        client.invalidateQueries({ queryKey: QUERY_KEYS.captureItems, exact: true }),
      ])
    },
  })

  return {
    ...mutation,
    mutate: (sourceId: string, options?: MutateOptions<SourceVisualJob, unknown, VisualMutationVariables>) =>
      mutation.mutate({ sourceId, requestId: requestId() }, options),
    mutateAsync: (sourceId: string, options?: MutateOptions<SourceVisualJob, unknown, VisualMutationVariables>) =>
      mutation.mutateAsync({ sourceId, requestId: requestId() }, options),
  }
}

export function useRefreshSourceVisual() {
  return useSourceVisualMutation('refresh')
}

export function useRemoveSourceVisual() {
  return useSourceVisualMutation('remove')
}

export function useRecentVisualSources(limit = 4) {
  const boundedLimit = Math.max(1, Math.min(4, Math.trunc(limit)))
  const sourceVisualsEnabled = useSourceVisualsEnabled()
  const enabled = isVisualSystemV2Enabled() && sourceVisualsEnabled
  return useQuery({
    queryKey: QUERY_KEYS.recentVisualSources(boundedLimit),
    queryFn: () => sourcesApi.list({ limit: boundedLimit, sort_by: 'updated', sort_order: 'desc' }),
    select: sources => sources.filter(source => source.visual !== null),
    enabled,
    staleTime: 60_000,
  })
}
