'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { evaluationsApi, type EvaluationRecheckRequest } from '@/lib/api/evaluations'

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

export function useRecheckEvaluation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: EvaluationRecheckRequest) => evaluationsApi.recheck(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['evaluation', data.run.id, data.run.notebook_id], data)
    },
  })
}
