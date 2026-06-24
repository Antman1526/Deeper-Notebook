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
import { notebooksApi } from '@/lib/api/notebooks'
import { sourcesApi } from '@/lib/api/sources'
import {
  studioApi,
  StudioArtifact,
  StudioArtifactCreate,
  StudioArtifactUpdate,
  StudioWorkflowRun,
  StudioWorkflowRunCreate,
  StudioGenerateOptions,
  StudioGenerateResponse,
} from '@/lib/api/studio'
import type { NotebookResponse, SourceResponse } from '@/lib/types/api'

export interface StudioCoursePackOptions {
  files: File[]
  links?: string[]
  title?: string
  autoGenerate?: boolean
  sourceReadinessTimeoutMs?: number
  sourceReadinessPollMs?: number
}

export interface StudioCoursePackResponse {
  notebook: NotebookResponse
  sources: SourceResponse[]
  artifact: StudioArtifact
  warnings: string[]
  generationStatus: 'queued' | 'pending' | 'failed'
}

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

export function useStudioCoursePack() {
  const queryClient = useQueryClient()

  return useMutation<StudioCoursePackResponse, Error, StudioCoursePackOptions>({
    mutationFn: async ({
      files,
      links = [],
      title,
      autoGenerate = true,
      sourceReadinessTimeoutMs = 60_000,
      sourceReadinessPollMs = 2_000,
    }) => {
      const cleanLinks = links.map((link) => link.trim()).filter(Boolean)
      if (files.length === 0 && cleanLinks.length === 0) {
        throw new Error('At least one file or link is required')
      }

      const firstSourceName = files[0]?.name ?? cleanLinks[0]
      const notebookTitle = title?.trim() || `Course Pack - ${firstSourceName}`
      const notebook = await notebooksApi.create({
        name: notebookTitle,
        description: 'Instructor-ready Course Pack queued from Studio sources.',
      })

      const sharedProvenance = {
        origin: 'studio_course_pack',
        workflow: 'course_pack',
      }

      const fileSources = await Promise.all(files.map((file) => (
        sourcesApi.create({
          type: 'upload',
          file,
          notebooks: [notebook.id],
          notebook_id: notebook.id,
          title: file.name,
          source_type: 'upload',
          provenance: {
            ...sharedProvenance,
            source_name: file.name,
          },
          embed: true,
          delete_source: false,
          async_processing: true,
        })
      )))

      const linkSources = await Promise.all(cleanLinks.map((url) => (
        sourcesApi.create({
          type: 'link',
          url,
          notebooks: [notebook.id],
          notebook_id: notebook.id,
          title: url,
          source_type: 'link',
          provenance: {
            ...sharedProvenance,
            source_url: url,
          },
          embed: true,
          delete_source: false,
          async_processing: true,
        })
      )))

      const sources = [...fileSources, ...linkSources]
      const artifact = await studioApi.createArtifact({
        notebook_id: notebook.id,
        artifact_type: 'course_pack',
        title: `${notebookTitle} Course Pack`,
        source_ids: sources.map((source) => source.id),
      })

      const warnings = sources
        .filter((source) => source.status === 'failed')
        .map((source) => `${source.title ?? source.id} failed to queue`)
      let generationStatus: StudioCoursePackResponse['generationStatus'] = 'pending'

      if (autoGenerate && warnings.length === 0) {
        const readiness = await waitForCoursePackSources(
          sources.map((source) => source.id),
          {
            timeoutMs: sourceReadinessTimeoutMs,
            pollMs: sourceReadinessPollMs,
          },
        )
        if (readiness.failed.length > 0) {
          warnings.push(`${readiness.failed.length} source(s) failed during processing`)
          generationStatus = 'failed'
        } else if (readiness.ready) {
          try {
            await studioApi.createWorkflowRun(artifact.id, {
              title: `Generate ${artifact.title}`,
              source_ids: sources.map((source) => source.id),
              approval_required: false,
            })
            generationStatus = 'queued'
          } catch (error) {
            if (isSourcesNotReadyError(error)) {
              warnings.push('Sources are queued. Course Pack generation will be ready from the notebook once extraction finishes.')
            } else {
              throw error
            }
          }
        } else {
          warnings.push('Sources are still processing. Open the notebook to generate the Course Pack when extraction finishes.')
        }
      }

      return {
        notebook,
        sources,
        artifact,
        warnings,
        generationStatus,
      }
    },
    onSuccess: ({ notebook, artifact }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebook(notebook.id) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.sources(notebook.id) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebook.id) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioWorkflowRuns(artifact.id) })
    },
  })
}

async function waitForCoursePackSources(
  sourceIds: string[],
  {
    timeoutMs,
    pollMs,
  }: {
    timeoutMs: number
    pollMs: number
  },
): Promise<{ ready: boolean; failed: string[] }> {
  if (sourceIds.length === 0) return { ready: true, failed: [] }

  const deadline = Date.now() + Math.max(0, timeoutMs)
  const interval = Math.max(100, pollMs)

  while (true) {
    const statuses = await Promise.all(
      sourceIds.map(async (sourceId) => ({
        sourceId,
        status: (await sourcesApi.status(sourceId)).status,
      })),
    )
    const failed = statuses
      .filter((item) => item.status === 'failed')
      .map((item) => item.sourceId)
    if (failed.length > 0) return { ready: false, failed }
    const processing = statuses.some((item) => (
      item.status === 'new'
      || item.status === 'queued'
      || item.status === 'running'
      || !item.status
    ))
    if (!processing) return { ready: true, failed: [] }
    if (Date.now() >= deadline) return { ready: false, failed: [] }
    await sleep(Math.min(interval, Math.max(0, deadline - Date.now())))
  }
}

function isSourcesNotReadyError(error: unknown): boolean {
  const detail = (error as {
    response?: { data?: { detail?: { code?: string } } }
  })?.response?.data?.detail
  return detail?.code === 'sources_not_ready'
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
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

export function useUpdateStudioArtifact(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation<
    StudioArtifact,
    Error,
    { artifactId: string; payload: StudioArtifactUpdate }
  >({
    mutationFn: ({ artifactId, payload }) => studioApi.updateArtifact(artifactId, payload),
    onSuccess: (artifact) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifactRevisions(artifact.id) })
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
