import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notebooksApi } from '@/lib/api/notebooks'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import {
  CreateNotebookRequest,
  UpdateNotebookRequest,
  NotebookImportPreviewRequest,
  NotebookImportPreviewResponse,
  NotebookImportRequest,
  NotebookImportResponse,
  NotebookVectorizeRequest,
  NotebookVectorizeResponse,
} from '@/lib/types/api'

export function useNotebooks(archived?: boolean) {
  return useQuery({
    queryKey: [...QUERY_KEYS.notebooks, { archived }],
    queryFn: () => notebooksApi.list({ archived, order_by: 'updated desc' }),
  })
}

export function useNotebook(id: string) {
  return useQuery({
    queryKey: QUERY_KEYS.notebook(id),
    queryFn: () => notebooksApi.get(id),
    enabled: !!id,
  })
}

export function useCreateNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateNotebookRequest) => notebooksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('notebooks.createSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useUpdateNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateNotebookRequest }) =>
      notebooksApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebook(id) })
      toast({
        title: t('common.success'),
        description: t('notebooks.updateSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useNotebookDeletePreview(id: string, enabled: boolean = false) {
  return useQuery({
    queryKey: [...QUERY_KEYS.notebook(id), 'delete-preview'],
    queryFn: () => notebooksApi.deletePreview(id),
    enabled: !!id && enabled,
  })
}

// v0.7.119 — Dry-run an import. We use useMutation rather than useQuery
// because the call is user-triggered ("Preview" button) and shouldn't
// auto-run on path change.
export function useImportPreview() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation<
    NotebookImportPreviewResponse,
    unknown,
    NotebookImportPreviewRequest
  >({
    mutationFn: (data) => notebooksApi.importPreview(data),
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

// v0.7.119 — Commit an import. Invalidates notebooks + sources so the
// new notebook + its sources show up immediately.
export function useImportNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation<NotebookImportResponse, unknown, NotebookImportRequest>({
    mutationFn: (data) => notebooksApi.importNotebook(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notebook(response.notebook_id),
      })
      toast({
        title: t('common.success'),
        description: t('notebooks.import.successToast')
          .replace('{notes}', String(response.note_ids.length))
          .replace('{sources}', String(response.source_ids.length)),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

// v0.7.119 — Bulk vectorize every Source attached to a notebook.
// Fire-and-forget so the toast shows the queued/skipped tally
// immediately; per-source progress is observable via /commands/{id}.
export function useVectorizeNotebookSources() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation<
    NotebookVectorizeResponse,
    unknown,
    { notebookId: string; data?: NotebookVectorizeRequest }
  >({
    mutationFn: ({ notebookId, data }) =>
      notebooksApi.vectorizeSources(notebookId, data),
    onSuccess: (response) => {
      // Source embed status may flip from missing → present once the
      // worker finishes; keep the lists fresh.
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast({
        title: t('common.success'),
        description: t('notebooks.bulkVectorize.successToast')
          .replace('{queued}', String(response.queued))
          .replace('{skipped}', String(response.skipped)),
      })
      if (response.warnings.length > 0) {
        toast({
          title: t('common.warning'),
          description: response.warnings.join('\n'),
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteNotebook() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({
      id,
      deleteExclusiveSources = false,
    }: {
      id: string
      deleteExclusiveSources?: boolean
    }) => notebooksApi.delete(id, deleteExclusiveSources),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      // Also invalidate sources since some may have been deleted
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast({
        title: t('common.success'),
        description: t('notebooks.deleteSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}