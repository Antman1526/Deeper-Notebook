import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ default: { get }, apiClient: { get } }))

import { useMCPServers } from './use-mcp-servers'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

// v0.8.130 — the chat's tool picker calls `.filter` on this list. An unexpected
// body (an error object, `{}`) used to crash the whole notebook view into the
// Recovery Center; a non-array now reads as "no servers".
describe('useMCPServers', () => {
  it('returns the server list', async () => {
    get.mockResolvedValueOnce({ data: [{ name: 'files', enabled: true }] })
    const { result } = renderHook(() => useMCPServers(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([{ name: 'files', enabled: true }])
  })

  it('treats a non-array response as no servers', async () => {
    get.mockResolvedValueOnce({ data: {} })
    const { result } = renderHook(() => useMCPServers(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })
})
