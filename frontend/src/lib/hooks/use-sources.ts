import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'
import { sourcesApi } from '@/lib/api/sources'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import {
  CreateSourceRequest,
  UpdateSourceRequest,
  SourceResponse,
  SourceStatusResponse,
  SourceListResponse
} from '@/lib/types/api'

// v0.7.191 — Predicate for "all source LIST queries" that excludes
// the per-source polling status keys `['sources', sourceId, 'status']`.
// Broad `invalidateQueries({ queryKey: ['sources'] })` matched those
// status polls too — every mutation triggered a status refetch for
// every source the user had open, even completed ones. On a notebook
// with 30+ sources this was a measurable hit.
//
// Any list-shape key (`['sources']`, `['sources', notebookId]`,
// `['sources', 'infinite', notebookId]`) doesn't include 'status';
// per-source status polls do. The substring check is robust to
// future key extensions as long as they keep the convention.
const _isSourcesListQuery = (queryKey: readonly unknown[]): boolean => {
  if (queryKey[0] !== 'sources') return false
  return !queryKey.includes('status')
}

const NOTEBOOK_SOURCES_PAGE_SIZE = 30

export function useSources(notebookId?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.sources(notebookId),
    queryFn: () => sourcesApi.list({ notebook_id: notebookId }),
    enabled: !!notebookId,
    // v0.7.159 — Raised from 5s → 60s and disabled refetchOnWindowFocus.
    // The sources list endpoint fans out to a per-row insights_count +
    // embedded-LIMIT-1 subquery (api/routers/sources.py); on a 200-source
    // notebook that's ~200 subqueries per refetch. Previous 5s + focus-
    // refetch combination meant every Cmd-Tab back to the app re-ran the
    // entire fan-out. Source mutations still trigger broad cache invalidation
    // (useCreateSource, useDeleteSource, useUpdateSource), so the user
    // doesn't lose accuracy — only the redundant on-focus refetch.
    // useSourceStatus (the polling hook) keeps its own short interval
    // for in-progress imports.
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Hook for fetching notebook sources with infinite scroll pagination.
 * Returns flattened sources array and pagination controls.
 */
export function useNotebookSources(notebookId: string) {
  const queryClient = useQueryClient()

  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.sourcesInfinite(notebookId),
    queryFn: async ({ pageParam = 0 }) => {
      const data = await sourcesApi.list({
        notebook_id: notebookId,
        limit: NOTEBOOK_SOURCES_PAGE_SIZE,
        offset: pageParam,
        sort_by: 'updated',
        sort_order: 'desc',
      })
      return {
        sources: data,
        nextOffset: data.length === NOTEBOOK_SOURCES_PAGE_SIZE ? pageParam + data.length : undefined,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    enabled: !!notebookId,
    // v0.7.159 — Same rationale as useSources: 5s+focus refetch
    // triggered repeated heavy fan-outs on tab switches. Mutations
    // explicitly invalidate this query key; that path stays accurate.
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  })

  // Flatten all pages into a single array (memoized to prevent infinite re-renders)
  const sources: SourceListResponse[] = useMemo(
    () => query.data?.pages.flatMap(page => page.sources) ?? [],
    [query.data?.pages]
  )

  // Refetch function that resets to first page
  const refetch = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sourcesInfinite(notebookId) })
  }, [queryClient, notebookId])

  return {
    sources,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: query.fetchNextPage,
    refetch,
    error: query.error,
  }
}

export function useSource(id: string) {
  return useQuery({
    queryKey: QUERY_KEYS.source(id),
    queryFn: () => sourcesApi.get(id),
    enabled: !!id,
    staleTime: 30 * 1000, // 30 seconds - shorter stale time for more responsive updates
    refetchOnWindowFocus: true, // Refetch when user comes back to the tab
  })
}

export function useCreateSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateSourceRequest) => sourcesApi.create(data),
    onSuccess: (result: SourceResponse, variables) => {
      // Invalidate queries for all relevant notebooks with immediate refetch
      if (variables.notebooks) {
        variables.notebooks.forEach(notebookId => {
          queryClient.invalidateQueries({
            queryKey: QUERY_KEYS.sources(notebookId),
            refetchType: 'active'
          })
          queryClient.invalidateQueries({
            queryKey: QUERY_KEYS.sourcesInfinite(notebookId),
            refetchType: 'active'
          })
        })
      } else if (variables.notebook_id) {
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.sources(variables.notebook_id),
          refetchType: 'active'
        })
        queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.sourcesInfinite(variables.notebook_id),
          refetchType: 'active'
        })
      }

      // Invalidate general sources query too with immediate refetch
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.sources(),
        refetchType: 'active'
      })

      // v0.7.166 — Also invalidate the notebooks list query.
      // `GET /notebooks` returns `source_count` and `note_count` per
      // notebook (api/routers/notebooks.py:53-59) for the sidebar.
      // Without this invalidation the sidebar showed stale counts
      // until the next window-focus refetch — visible UX bug after
      // every source-add.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })

      // Show different messages based on processing mode
      if (variables.async_processing) {
        toast({
          title: t('sources.sourceQueued'),
          description: t('sources.sourceQueuedDesc'),
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('sources.sourceAddedSuccess'),
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToAddSource')),
        variant: 'destructive',
      })
    },
  })
}

export function useUpdateSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateSourceRequest }) =>
      sourcesApi.update(id, data),
    onSuccess: (_, { id }) => {
      // Invalidate ALL sources queries (both general and notebook-specific)
      queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery(q.queryKey) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(id) })
      toast({
        title: t('common.success'),
        description: t('sources.sourceUpdatedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToUpdateSource')),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteSource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => sourcesApi.delete(id),
    onSuccess: (_, id) => {
      // Invalidate ALL sources queries (both general and notebook-specific)
      queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery(q.queryKey) })
      // Also invalidate the specific source
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(id) })
      // v0.7.166 — Invalidate the notebooks list so the sidebar's
      // source_count refreshes. Same rationale as in useCreateSource.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('sources.sourceDeletedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToDeleteSource')),
        variant: 'destructive',
      })
    },
  })
}

export function useFileUpload() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ file, notebookId }: { file: File; notebookId: string }) =>
      sourcesApi.upload(file, notebookId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.sources(variables.notebookId)
      })
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.sourcesInfinite(variables.notebookId),
        refetchType: 'active'
      })
      // v0.7.166 — sidebar source_count refresh; see useCreateSource.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('sources.fileUploadedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToUploadFile')),
        variant: 'destructive',
      })
    },
  })
}

export function useSourceStatus(sourceId: string, enabled = true) {
  return useQuery({
    queryKey: ['sources', sourceId, 'status'],
    queryFn: () => sourcesApi.status(sourceId),
    enabled: !!sourceId && enabled,
    refetchInterval: (query) => {
      // Auto-refresh every 2 seconds if processing
      // The query.state.data contains the SourceStatusResponse
      const data = query.state.data as SourceStatusResponse | undefined
      if (data?.status === 'running' || data?.status === 'queued' || data?.status === 'new') {
        return 2000
      }
      // No auto-refresh if completed, failed, or unknown
      return false
    },
    staleTime: 0, // Always consider status data stale for real-time updates
    retry: (failureCount, error) => {
      // Don't retry on 404 (source not found)
      const axiosError = error as { response?: { status?: number } }
      if (axiosError?.response?.status === 404) {
        return false
      }
      return failureCount < 3
    },
  })
}

export function useRetrySource() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (sourceId: string) => sourcesApi.retry(sourceId),
    onSuccess: (result, sourceId) => {
      // Invalidate status query to refetch latest status
      queryClient.invalidateQueries({
        queryKey: ['sources', sourceId, 'status']
      })
      // Invalidate ALL sources queries to refresh the UI
      queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery(q.queryKey) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })

      toast({
        title: t('sources.sourceRequeued'),
        description: t('sources.sourceRequeuedDesc'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToRetry')),
        variant: 'destructive',
      })
    },
  })
}

export function useAddSourcesToNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async ({ notebookId, sourceIds }: { notebookId: string; sourceIds: string[] }) => {
      const { notebooksApi } = await import('@/lib/api/notebooks')

      // Use Promise.allSettled to handle partial failures gracefully
      const results = await Promise.allSettled(
        sourceIds.map(sourceId => notebooksApi.addSource(notebookId, sourceId))
      )

      // Count successes and failures
      const successes = results.filter(r => r.status === 'fulfilled').length
      const failures = results.filter(r => r.status === 'rejected').length

      return { successes, failures, total: sourceIds.length }
    },
    onSuccess: (result, { notebookId, sourceIds }) => {
      // Invalidate ALL sources queries to refresh all lists
      queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery(q.queryKey) })
      // Specifically invalidate the notebook's sources
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(notebookId) })
      // Invalidate each affected source
      sourceIds.forEach(sourceId => {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      })
      // v0.7.166 — sidebar source_count refresh; see useCreateSource.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })

      // Show appropriate toast based on results
      if (result.failures === 0) {
        toast({
          title: t('common.success'),
          description: t('sources.sourcesAddedToNotebook').replace('{count}', result.successes.toString()),
        })
      } else if (result.successes === 0) {
        toast({
          title: t('common.error'),
          description: t('sources.failedToAddSourcesToNotebook'),
          variant: 'destructive',
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('sources.partialAddSuccess')
            .replace('{success}', result.successes.toString())
            .replace('{failed}', result.failures.toString()),
          variant: 'default',
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToAddSourcesToNotebook')),
        variant: 'destructive',
      })
    },
  })
}

export function useRemoveSourceFromNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: async ({ notebookId, sourceId }: { notebookId: string; sourceId: string }) => {
      // This will call the API we created
      const { notebooksApi } = await import('@/lib/api/notebooks')
      return notebooksApi.removeSource(notebookId, sourceId)
    },
    onSuccess: (_, { notebookId, sourceId }) => {
      // Invalidate ALL sources queries to refresh all lists
      queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery(q.queryKey) })
      // Specifically invalidate the notebook's sources
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(notebookId) })
      // Also invalidate the specific source
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.source(sourceId) })
      // v0.7.166 — sidebar source_count refresh; see useCreateSource.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })

      toast({
        title: t('common.success'),
        description: t('sources.sourceRemovedFromNotebook'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), t('sources.failedToRemoveSourceFromNotebook')),
        variant: 'destructive',
      })
    },
  })
}
