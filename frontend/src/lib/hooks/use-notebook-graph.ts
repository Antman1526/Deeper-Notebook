'use client'

// v0.8.83 — mind-map graph hook (improvement roadmap, Batch 3). Fetches the
// notebook's hub-and-spoke graph (notebook + sources + notes) for the React
// Flow mind map. Only enabled when the consumer opts in (e.g. the dialog is
// open) so we don't fetch the graph on every notebook view.
import { useQuery } from '@tanstack/react-query'

import { notebooksApi } from '@/lib/api/notebooks'
import { QUERY_KEYS } from '@/lib/api/query-client'

export function useNotebookGraph(notebookId: string, enabled = true) {
  return useQuery({
    queryKey: [...QUERY_KEYS.notebook(notebookId), 'graph'],
    queryFn: () => notebooksApi.getGraph(notebookId),
    enabled: enabled && !!notebookId,
  })
}
