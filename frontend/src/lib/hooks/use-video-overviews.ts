'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import { videoOverviewsApi, type VideoOverviewComposeRequest } from '@/lib/api/video-overviews'

export function useComposeVideoOverview(notebookId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: VideoOverviewComposeRequest) => videoOverviewsApi.compose(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studioArtifacts(notebookId) })
    },
  })
}
