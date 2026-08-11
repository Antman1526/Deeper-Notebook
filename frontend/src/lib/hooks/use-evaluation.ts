'use client'

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'

import {
  evaluationsApi,
  type EvaluationRecheckRequest,
  type EvaluationSelector,
} from '@/lib/api/evaluations'

const EVALUATION_PERSISTENCE_GRACE_MS = 15_000

export function evaluationPersistencePendingKey(notebookId: string, messageId: string) {
  return ['evaluations', 'persistence-pending', notebookId, messageId] as const
}

export function markEvaluationPersistencePending(
  queryClient: QueryClient,
  notebookId: string,
  messageId: string,
) {
  queryClient.setQueryData(
    evaluationPersistencePendingKey(notebookId, messageId),
    Date.now(),
  )
  void queryClient.invalidateQueries({
    queryKey: ['evaluations', 'latest', 'messages', notebookId],
  })
}

export function useEvaluation(runId?: string, notebookId?: string) {
  return useQuery({
    queryKey: ['evaluation', runId, notebookId],
    queryFn: () => evaluationsApi.get(runId!, notebookId!),
    enabled: Boolean(runId && notebookId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 1_500 : false
    },
  })
}

export function useLatestEvaluation(
  notebookId?: string,
  selector?: EvaluationSelector,
) {
  const artifactId = selector?.artifactId
  const messageId = selector?.messageId
  const hasExactlyOneSelector = Boolean(artifactId) !== Boolean(messageId)
  return useQuery({
    queryKey: ['evaluation', 'latest', notebookId, artifactId, messageId],
    queryFn: () => evaluationsApi.latest(notebookId!, { artifactId, messageId }),
    enabled: Boolean(notebookId && hasExactlyOneSelector),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 1_500 : false
    },
  })
}

export function useLatestMessageEvaluations(
  notebookId: string | undefined,
  messageIds: string[],
) {
  const queryClient = useQueryClient()
  const uniqueMessageIds = [...new Set(messageIds)]
  return useQuery({
    queryKey: ['evaluations', 'latest', 'messages', notebookId, uniqueMessageIds],
    queryFn: async () => {
      const data = await evaluationsApi.latestBatch(notebookId!, uniqueMessageIds)
      const now = Date.now()
      for (const messageId of uniqueMessageIds) {
        const key = evaluationPersistencePendingKey(notebookId!, messageId)
        const pendingSince = queryClient.getQueryData<number>(key)
        if (
          data[messageId]
          || (typeof pendingSince === 'number'
            && now - pendingSince >= EVALUATION_PERSISTENCE_GRACE_MS)
        ) {
          queryClient.removeQueries({ queryKey: key, exact: true })
        }
      }
      return data
    },
    enabled: Boolean(notebookId && uniqueMessageIds.length > 0),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data
      const hasPersistencePending = uniqueMessageIds.some((messageId) => {
        const pendingSince = queryClient.getQueryData<number>(
          evaluationPersistencePendingKey(notebookId!, messageId),
        )
        return typeof pendingSince === 'number'
          && Date.now() - pendingSince < EVALUATION_PERSISTENCE_GRACE_MS
      })
      if (hasPersistencePending) return 1_500
      if (!data) return false
      return Object.values(data).some(
        (evaluation) => evaluation.status === 'pending' || evaluation.status === 'running',
      ) ? 1_500 : false
    },
  })
}

export function useRecheckEvaluation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: EvaluationRecheckRequest) => evaluationsApi.recheck(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['evaluation', data.run.id, data.run.notebook_id], data)
    },
  })
}
