import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { vaultApi } from '@/lib/api/vault'

export const vaultKeys = {
  all: ['vaults'] as const,
  detail: (id: string) => ['vaults', id] as const,
  files: (id: string) => ['vaults', id, 'files'] as const,
  canvas: (id: string, relativePath: string) => ['vaults', id, 'canvases', relativePath] as const,
  page: (id: string, noteId: string) => ['vaults', id, 'pages', noteId] as const,
  backlinks: (id: string, noteId: string) => ['vaults', id, 'pages', noteId, 'backlinks'] as const,
  graph: (id: string, centerNoteId?: string) => centerNoteId ? ['vaults', id, 'graph', centerNoteId] as const : ['vaults', id, 'graph'] as const,
}

export function useVaults() { return useQuery({ queryKey: vaultKeys.all, queryFn: vaultApi.list }) }
export function useVaultFiles(vaultId?: string) { return useQuery({ queryKey: vaultKeys.files(vaultId ?? ''), queryFn: () => vaultApi.files(vaultId!), enabled: Boolean(vaultId) }) }
export function useVaultCanvas(vaultId?: string, relativePath?: string, enabled = true) {
  return useQuery({
    queryKey: vaultKeys.canvas(vaultId ?? '', relativePath ?? ''),
    queryFn: () => vaultApi.canvas(vaultId!, relativePath!),
    enabled: Boolean(vaultId && relativePath && enabled),
  })
}
export function useVaultPage(vaultId?: string, noteId?: string) { return useQuery({ queryKey: vaultKeys.page(vaultId ?? '', noteId ?? ''), queryFn: () => vaultApi.page(vaultId!, noteId!), enabled: Boolean(vaultId && noteId) }) }
export function useVaultPagePreview(vaultId?: string, noteId?: string, enabled = false) {
  return useQuery({
    queryKey: vaultKeys.page(vaultId ?? '', noteId ?? ''),
    queryFn: () => vaultApi.page(vaultId!, noteId!),
    enabled: Boolean(vaultId && noteId && enabled),
    staleTime: 30_000,
  })
}
export function useVaultBacklinks(vaultId?: string, noteId?: string) { return useQuery({ queryKey: vaultKeys.backlinks(vaultId ?? '', noteId ?? ''), queryFn: () => vaultApi.backlinks(vaultId!, noteId!), enabled: Boolean(vaultId && noteId) }) }
export function useVaultOutgoing(vaultId?: string, noteId?: string) { return useQuery({ queryKey: [...vaultKeys.page(vaultId ?? '', noteId ?? ''), 'outgoing'], queryFn: () => vaultApi.outgoing(vaultId!, noteId!), enabled: Boolean(vaultId && noteId) }) }
export function useVaultGraph(vaultId?: string, noteId?: string, enabled = true) { return useQuery({ queryKey: vaultKeys.graph(vaultId ?? '', noteId), queryFn: () => vaultApi.graph(vaultId!, noteId!), enabled: Boolean(vaultId && noteId && enabled) }) }

export function useScanVault(vaultId: string, noteId?: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => vaultApi.scan(vaultId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: vaultKeys.all }),
        client.invalidateQueries({ queryKey: vaultKeys.detail(vaultId) }),
        client.invalidateQueries({ queryKey: vaultKeys.files(vaultId) }),
        client.invalidateQueries({ queryKey: vaultKeys.graph(vaultId) }),
        client.invalidateQueries({ queryKey: ['search'] }),
        ...(noteId ? [client.invalidateQueries({ queryKey: vaultKeys.page(vaultId, noteId) }), client.invalidateQueries({ queryKey: vaultKeys.backlinks(vaultId, noteId) })] : []),
      ])
    },
  })
}
