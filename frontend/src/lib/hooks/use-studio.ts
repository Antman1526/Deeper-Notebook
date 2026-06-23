/**
 * ONP v0.7.0 — Studio mutation hook.
 *
 * Wraps studioApi.generate in a TanStack Query useMutation so the calling
 * component gets isPending / isError / data without managing local state.
 * Invalidates the notebooks list on success so the new notebook appears
 * immediately when the user navigates back.
 */
'use client'

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import {
  studioApi,
  StudioArtifact,
  StudioArtifactCreate,
  StudioWorkflowRun,
  StudioWorkflowRunCreate,
  StudioGenerateOptions,
  StudioGenerateResponse,
} from '@/lib/api/studio'

export function useStudioGenerate() {
  const queryClient = useQueryClient()
  return useMutation<StudioGenerateResponse, Error, StudioGenerateOptions>({
    mutationFn: studioApi.generate,
    onSuccess: () => {
      // The new notebook should appear in /notebooks immediately, and
      // (for notebook mode) its sources + the generated Note should be
      // visible. Broad invalidation is correct here since multiple
      // record types changed.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
    },
  })
}

export function useStudioArtifacts(
  notebookId: string,
  options: { enabled?: boolean } = {},
) {
  return useQuery<StudioArtifact[], Error>({
    queryKey: QUERY_KEYS.studioArtifacts(notebookId),
    queryFn: () => studioApi.listArtifacts(notebookId),
    enabled: Boolean(notebookId) && (options.enabled ?? true),
  })
}

export function useStudioArtifactRevisions(
  artifactId: string | null,
  options: { enabled?: boolean } = {},
) {
  return useQuery<StudioArtifact[], Error>({
    queryKey: QUERY_KEYS.studioArtifactRevisions(artifactId ?? ''),
    queryFn: () => studioApi.listArtifactRevisions(artifactId ?? ''),
    enabled: Boolean(artifactId) && (options.enabled ?? true),
  })
}

export function useStudioWorkflowRuns(
  artifactIds: string[],
  options: { enabled?: boolean } = {},
) {
  const uniqueArtifactIds = Array.from(new Set(artifactIds.filter(Boolean)))
  const queries = useQueries({
    queries: uniqueArtifactIds.map((artifactId) => ({
      queryKey: QUERY_KEYS.studioWorkflowRuns(artifactId),
      queryFn: () => studioApi.listWorkflowRuns(artifactId),
      enabled: (options.enabled ?? true) && uniqueArtifactIds.length > 0,
      refetchInterval: (query: { state: { data?: StudioWorkflowRun[] } }) => {
        const runs = query.state.data
        return runs?.some((run) => (
          run.status === 'queued'
          || run.status === 'running'
          || run.status === 'awaiting_approval'
        ))
          ? 3000
          : false
      },
    })),
  })

  return {
    data: queries.flatMap((query) => query.data ?? []),
    isLoading: queries.some((query) => query.isLoading),
    isFetching: queries.some((query) => query.isFetching),
  }
}

export function useCreateStudioArtifact(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<StudioArtifact, Error, StudioArtifactCreate>({
    mutationFn: studioApi.createArtifact,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
    },
  })
}

export function useCreateStudioWorkflowRun(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<
    StudioWorkflowRun,
    Error,
    { artifactId: string; payload: StudioWorkflowRunCreate }
  >({
    mutationFn: ({ artifactId, payload }) => studioApi.createWorkflowRun(artifactId, payload),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioWorkflowRuns(run.artifact_id) })
    },
  })
}

export function useGenerateStudioArtifact(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<StudioArtifact, Error, string>({
    mutationFn: studioApi.generateArtifact,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
      queryClient.invalidateQueries({ queryKey: ['studio', 'artifacts'] })
    },
  })
}

export function useApproveStudioWorkflowRun(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<StudioWorkflowRun, Error, string>({
    mutationFn: studioApi.approveWorkflowRun,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioWorkflowRuns(run.artifact_id) })
    },
  })
}

export function useDeleteStudioArtifact(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<{ deleted: boolean; id: string }, Error, string>({
    mutationFn: studioApi.deleteArtifact,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
    },
  })
}
