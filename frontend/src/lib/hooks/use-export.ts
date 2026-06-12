// v0.7.105 — Mutations for the two export endpoints. Toasts on success/error
// using the same pattern as use-notebooks.ts. We deliberately surface
// raw error messages from the backend (overwrite=false collisions,
// permission denied, etc.) instead of swallowing them.

import { useMutation } from '@tanstack/react-query'
import { exportsApi } from '@/lib/api/exports'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import {
  ExportResponse,
  NotebookExportRequest,
  NoteExportRequest,
} from '@/lib/types/api'

export function useExportNotebook() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation<
    ExportResponse,
    unknown,
    { id: string; data: NotebookExportRequest }
  >({
    mutationFn: ({ id, data }) => exportsApi.exportNotebook(id, data),
    onSuccess: (response) => {
      toast({
        title: t('notebooks.exportSuccess'),
        description: response.destination,
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
        title: t('notebooks.exportFailure'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}

export function useExportNote() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation<
    ExportResponse,
    unknown,
    { id: string; data: NoteExportRequest }
  >({
    mutationFn: ({ id, data }) => exportsApi.exportNote(id, data),
    onSuccess: (response) => {
      toast({
        title: t('notes.exportSuccess'),
        description: response.destination,
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('notes.exportFailure'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    },
  })
}
