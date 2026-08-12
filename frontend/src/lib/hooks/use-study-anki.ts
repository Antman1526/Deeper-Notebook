'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { studyAnkiApi } from '@/lib/api/study-anki'
import { QUERY_KEYS } from '@/lib/api/query-client'
import type { AnkiHttpOptions } from '@/lib/types/study-anki'

export function useStudyAnkiImportPreview() {
  return useMutation({
    mutationFn: ({ planId, file, options, onUploadProgress }: { planId: string; file: File; options?: AnkiHttpOptions; onUploadProgress?: (percent: number) => void }) =>
      studyAnkiApi.preview(planId, file, options, onUploadProgress),
  })
}

export function useStudyAnkiImportStatus(planId: string | null | undefined, jobId: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.studyAnkiJob(planId ?? '', jobId ?? ''),
    queryFn: () => studyAnkiApi.status(planId as string, jobId as string),
    enabled: Boolean(planId && jobId),
    refetchInterval: (query) => query.state.data?.status === 'preview_ready' || query.state.data?.status === 'published' ? false : 1000,
  })
}

export function useStudyAnkiPublish() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, jobId, requestId, options }: { planId: string; jobId: string; requestId: string; options?: AnkiHttpOptions }) =>
      studyAnkiApi.publish(planId, jobId, requestId, options),
    onSuccess: async (_result, { planId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlan(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlanProgress(planId) }),
      ])
    },
  })
}

export function useStudyAnkiExport() {
  return useMutation({ mutationFn: ({ planId, options }: { planId: string; options?: AnkiHttpOptions }) => studyAnkiApi.export(planId, options) })
}
