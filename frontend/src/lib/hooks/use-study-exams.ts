'use client'

// v0.8.97 — ExamLab hooks: start / take / submit / seed misses.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import { studyExamsApi } from '@/lib/api/study-exams'

export function useExamAttempts(notebookId?: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.studyExamAttempts(notebookId),
    queryFn: () => studyExamsApi.listRecent(notebookId),
    enabled,
  })
}

export function useExamAttempt(attemptId: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.studyExamAttempt(attemptId ?? 'none'),
    queryFn: () => studyExamsApi.get(attemptId as string),
    enabled: Boolean(attemptId),
  })
}

export function useStartExam() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ artifactId, durationSec }: { artifactId: string; durationSec: number }) =>
      studyExamsApi.start(artifactId, durationSec),
    onSuccess: (attempt) => {
      queryClient.setQueryData(QUERY_KEYS.studyExamAttempt(attempt.id), attempt)
      queryClient.invalidateQueries({ queryKey: ['study', 'exams', 'attempts'] })
    },
  })
}

export function useSubmitExam() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ attemptId, answers }: { attemptId: string; answers: Record<string, string> }) =>
      studyExamsApi.submit(attemptId, answers),
    onSuccess: (attempt) => {
      queryClient.setQueryData(QUERY_KEYS.studyExamAttempt(attempt.id), attempt)
      queryClient.invalidateQueries({ queryKey: ['study', 'exams', 'attempts'] })
    },
  })
}

export function useSeedExamMisses() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (attemptId: string) => studyExamsApi.seedMisses(attemptId),
    onSuccess: (_result, attemptId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyExamAttempt(attemptId) })
      // New cards land in the review deck.
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyDue })
    },
  })
}
