// v0.8.0 Phase 2 Task 10 — MCP servers CRUD hooks.
// Backs the /settings/mcp page. Patterned after use-credentials.ts:
// query key constant, one query hook, three mutation hooks with
// toast feedback. Toasts use sonner directly (not the useToast
// wrapper) to stay consistent with the page-level toast usage
// established by use-search.ts and useNotebookChat.ts.
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api/client'
import { useTranslation } from '@/lib/hooks/use-translation'

// ---------------------------------------------------------------------------
// Types matching api/routers/mcp.py response shapes
// ---------------------------------------------------------------------------
export interface MCPServer {
  id: string
  name: string
  url: string
  enabled: boolean
}

export interface MCPTestResult {
  ok: boolean
  tools?: string[]
  error?: string
}

export interface CreateMCPServerRequest {
  name: string
  url: string
  enabled?: boolean
}

// ---------------------------------------------------------------------------
// Query key
// ---------------------------------------------------------------------------
export const MCP_QUERY_KEYS = {
  all: ['mcp', 'servers'] as const,
}

// ---------------------------------------------------------------------------
// Query hook — list
// ---------------------------------------------------------------------------
export function useMCPServers() {
  return useQuery<MCPServer[]>({
    queryKey: MCP_QUERY_KEYS.all,
    queryFn: async () => {
      const res = await apiClient.get<MCPServer[]>('/mcp')
      return res.data
    },
  })
}

// ---------------------------------------------------------------------------
// Mutation — create
// ---------------------------------------------------------------------------
export function useCreateMCPServer() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation<MCPServer, Error, CreateMCPServerRequest>({
    mutationFn: async (data) => {
      const res = await apiClient.post<MCPServer>('/mcp', data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.all })
      toast.success(t('settings.mcp.createSuccess'))
    },
    onError: (error: unknown) => {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t('settings.mcp.createFailed')
      toast.error(message)
    },
  })
}

// ---------------------------------------------------------------------------
// Mutation — test
// The endpoint returns {ok, tools?, error?}. We surface the result via
// toast so the page component stays clean (no local result state needed).
// ---------------------------------------------------------------------------
export function useTestMCPServer() {
  const { t } = useTranslation()

  return useMutation<MCPTestResult, Error, string>({
    mutationFn: async (id) => {
      const res = await apiClient.post<MCPTestResult>(`/mcp/${id}/test`)
      return res.data
    },
    onSuccess: (result) => {
      if (result.ok) {
        const count = result.tools?.length ?? 0
        toast.success(t('settings.mcp.testOk').replace('{count}', String(count)))
      } else {
        const errorMsg = result.error
          ? result.error.slice(0, 120)
          : t('settings.mcp.testFailed')
        toast.error(errorMsg)
      }
    },
    onError: (error: unknown) => {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t('settings.mcp.testFailed')
      toast.error(message)
    },
  })
}

// ---------------------------------------------------------------------------
// Mutation — delete
// ---------------------------------------------------------------------------
export function useDeleteMCPServer() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      await apiClient.delete(`/mcp/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.all })
      toast.success(t('settings.mcp.deleteSuccess'))
    },
    onError: (error: unknown) => {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t('settings.mcp.deleteFailed')
      toast.error(message)
    },
  })
}
