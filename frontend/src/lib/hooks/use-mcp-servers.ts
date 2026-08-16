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
  // v0.8.1 Item 5 — priority field added by migration 19; lower = higher
  // priority in the chat graph. Absent on records created before migration.
  priority?: number
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

// v0.8.1 Item 5 — partial-update payload for PATCH /api/mcp/{id}.
export interface UpdateMCPServerRequest {
  id: string
  body: {
    priority?: number
    enabled?: boolean
  }
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
// v0.8.65 — built-in web_search tool availability.
// The chat tool loop binds a `web_search` tool when a provider is available
// (a configured key/SearXNG URL, or the v0.8.82 keyless Wikipedia tail). It is
// NOT an MCP registry row, so the picker needs this signal to render a
// synthetic toggle. `provider` is a label (serper/tavily/searxng/wikipedia) —
// never a key. v0.8.82 — the same response reports the keyless
// `scholarly_search` tool so the picker can offer its off-switch too; the
// fields are optional so a cached pre-v0.8.82 response cannot crash the picker.
// ---------------------------------------------------------------------------
export interface WebSearchStatus {
  enabled: boolean
  provider: string | null
  tool_name: string
  scholarly_enabled?: boolean
  scholarly_tool_name?: string
}

export function useWebSearchStatus() {
  return useQuery<WebSearchStatus>({
    queryKey: ['mcp', 'web-search-status'],
    queryFn: async () => {
      const res = await apiClient.get<WebSearchStatus>('/mcp/web-search')
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
// Mutation — update (priority / enabled)  v0.8.1 Item 5
// PATCH /api/mcp/{id} — only the present fields are written.
// Invalidates the server list on success so the reordered rows re-render.
// ---------------------------------------------------------------------------
export function useUpdateMCPServer() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation<MCPServer, Error, UpdateMCPServerRequest>({
    mutationFn: async ({ id, body }) => {
      const res = await apiClient.patch<MCPServer>(`/mcp/${id}`, body)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.all })
    },
    onError: (error: unknown) => {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t('settings.mcp.updateFailed')
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
