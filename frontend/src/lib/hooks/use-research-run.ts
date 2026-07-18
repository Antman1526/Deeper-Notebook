import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { researchApi } from '@/lib/api/research'

const researchKey = (notebookId: string, runId: string) => ['research-run', notebookId, runId] as const

export function useResearchRun(notebookId: string, runId: string | null) {
  return useQuery({
    queryKey: researchKey(notebookId, runId ?? 'none'),
    queryFn: () => researchApi.get(notebookId, runId!),
    enabled: Boolean(notebookId && runId),
    refetchInterval: (query) => query.state.data?.stage === 'complete' || query.state.data?.cancelled ? false : 5_000,
  })
}

export function useResearchRunActions(notebookId: string, runId: string | null) {
  const queryClient = useQueryClient()
  const refresh = async () => {
    if (runId) await queryClient.invalidateQueries({ queryKey: researchKey(notebookId, runId) })
  }
  return {
    create: useMutation({ mutationFn: (objective: string) => researchApi.create(notebookId, objective) }),
    approve: useMutation({ mutationFn: (accepted: string[]) => researchApi.approve(notebookId, runId!, accepted), onSuccess: refresh }),
    cancel: useMutation({ mutationFn: () => researchApi.cancel(notebookId, runId!), onSuccess: refresh }),
    resume: useMutation({ mutationFn: () => researchApi.resume(notebookId, runId!), onSuccess: refresh }),
  }
}
