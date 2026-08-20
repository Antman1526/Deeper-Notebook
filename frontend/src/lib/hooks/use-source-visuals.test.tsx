import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/client', () => ({
  default: { get: vi.fn() },
}))

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: { list: vi.fn() },
}))

import apiClient from '@/lib/api/client'
import { sourcesApi } from '@/lib/api/sources'
import { resetRuntimeFeatures } from '@/lib/features'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useRuntimeFeatures } from './use-runtime-features'
import { useRecentVisualSources } from './use-source-visuals'

function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function createWrapper(client = createClient()) {
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

afterEach(() => {
  resetRuntimeFeatures()
  vi.clearAllMocks()
  delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
  delete process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS
})

describe('useRecentVisualSources default and rollback contract', () => {
  it('loads recent visual sources when both visual defaults are unset', async () => {
    vi.mocked(sourcesApi.list).mockResolvedValue([])

    renderHook(() => useRecentVisualSources(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(sourcesApi.list).toHaveBeenCalledWith({
        limit: 4,
        sort_by: 'updated',
        sort_order: 'desc',
      })
    })
  })

  it('does not load recent visual sources when both canonical build flags are explicitly off', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
    process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '0'

    renderHook(() => useRecentVisualSources(), { wrapper: createWrapper() })

    expect(sourcesApi.list).not.toHaveBeenCalled()
  })

  it('stops an already-mounted source query after a delayed backend rollback', async () => {
    const client = createClient()
    const response = deferred<{ data: { features: unknown } }>()
    vi.mocked(apiClient.get).mockReturnValue(response.promise)
    vi.mocked(sourcesApi.list).mockResolvedValue([])

    renderHook(() => {
      useRuntimeFeatures()
      return useRecentVisualSources()
    }, { wrapper: createWrapper(client) })

    await waitFor(() => expect(sourcesApi.list).toHaveBeenCalledTimes(1))

    await act(async () => {
      response.resolve({ data: { features: { sourceVisuals: false } } })
      await response.promise
    })

    await act(async () => {
      await client.invalidateQueries({ queryKey: QUERY_KEYS.recentVisualSources(4) })
    })

    expect(sourcesApi.list).toHaveBeenCalledTimes(1)
  })
})
