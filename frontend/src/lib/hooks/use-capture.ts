import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { captureApi } from '@/lib/api/capture'

const rootKey = ['capture', 'roots'] as const
const itemKey = ['capture', 'items'] as const

export function useCaptureRoots() { return useQuery({ queryKey: rootKey, queryFn: captureApi.roots }) }
export function useCaptureItems() { return useQuery({ queryKey: itemKey, queryFn: captureApi.items }) }
export function useCaptureActions() {
  const client = useQueryClient()
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: rootKey }), client.invalidateQueries({ queryKey: itemKey })])
  return {
    addRoot: useMutation({ mutationFn: captureApi.addRoot, onSuccess: refresh }),
    scan: useMutation({ mutationFn: (root?: string) => captureApi.scan(root), onSuccess: refresh }),
  }
}
