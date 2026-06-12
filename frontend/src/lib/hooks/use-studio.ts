/**
 * ONP v0.7.0 — Studio mutation hook.
 *
 * Wraps studioApi.generate in a TanStack Query useMutation so the calling
 * component gets isPending / isError / data without managing local state.
 * Invalidates the notebooks list on success so the new notebook appears
 * immediately when the user navigates back.
 */
'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import { studioApi, StudioGenerateOptions, StudioGenerateResponse } from '@/lib/api/studio'

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
