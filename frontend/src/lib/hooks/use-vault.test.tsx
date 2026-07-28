import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/vault', () => ({ vaultApi: { scan: vi.fn() } }))

import { vaultApi } from '@/lib/api/vault'
import { useScanVault, vaultKeys } from './use-vault'

const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('vault query cache', () => {
  it('uses stable vault query keys', () => {
    expect(vaultKeys.page('v', 'n')).toEqual(['vaults', 'v', 'pages', 'n'])
    expect(vaultKeys.backlinks('v', 'n')).toEqual(['vaults', 'v', 'pages', 'n', 'backlinks'])
  })

  it('invalidates vault views and global search after scanning', async () => {
    vi.mocked(vaultApi.scan).mockResolvedValue({ operation_id: 'scan:1', state: 'ready-read-only', observed: 1, parsed: 1, unchanged: 0, unsupported: 0, invalid: 0, missing: 0, embeddings_pending: 1 } as never)
    const { result } = renderHook(() => useScanVault('vault:one', 'note:one'), { wrapper })
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await act(async () => { await result.current.mutateAsync() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vaultKeys.detail('vault:one') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vaultKeys.files('vault:one') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vaultKeys.graph('vault:one') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vaultKeys.page('vault:one', 'note:one') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: vaultKeys.backlinks('vault:one', 'note:one') })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['search'] })
  })
})
