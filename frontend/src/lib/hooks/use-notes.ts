import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notesApi } from '@/lib/api/notes'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import { CreateNoteRequest, UpdateNoteRequest } from '@/lib/types/api'

export function useNotes(notebookId?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.notes(notebookId),
    queryFn: () => notesApi.list({ notebook_id: notebookId }),
    enabled: !!notebookId,
  })
}

export function useNote(id?: string, options?: { enabled?: boolean }) {
  const noteId = id ?? ''
  return useQuery({
    queryKey: QUERY_KEYS.note(noteId),
    queryFn: () => notesApi.get(noteId),
    enabled: !!noteId && (options?.enabled ?? true),
  })
}

export function useCreateNote() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateNoteRequest) => notesApi.create(data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.notes(variables.notebook_id)
      })
      // v0.7.166 — sidebar note_count refresh.
      // `GET /notebooks` returns note_count per notebook
      // (api/routers/notebooks.py:53-59); without this invalidation
      // the sidebar counter stayed stale until window-focus refetch.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('notebooks.noteCreatedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('notebooks.failedToCreateNote')),
        variant: 'destructive',
      })
    },
  })
}

export function useUpdateNote() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateNoteRequest }) =>
      notesApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes() })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.note(id) })
      // v0.7.189 — also invalidate the notebooks list so the sidebar's
      // "recently-updated" sort + the per-notebook last-activity
      // timestamp refresh. useCreateNote + useDeleteNote already do
      // this; useUpdateNote was the missing third side of the triangle.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('notebooks.noteUpdatedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('notebooks.failedToUpdateNote')),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteNote() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => notesApi.delete(id),
    onSuccess: () => {
      // Invalidate all notes queries (with and without notebook IDs)
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      // v0.7.166 — sidebar note_count refresh; see useCreateNote.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebooks })
      toast({
        title: t('common.success'),
        description: t('notebooks.noteDeletedSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('notebooks.failedToDeleteNote')),
        variant: 'destructive',
      })
    },
  })
}
