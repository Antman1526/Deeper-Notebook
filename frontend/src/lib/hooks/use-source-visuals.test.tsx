import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: { list: vi.fn() },
}))

import { sourcesApi } from '@/lib/api/sources'
import { applyRuntimeFeatures, resetRuntimeFeatures } from '@/lib/features'
import { useRecentVisualSources } from './use-source-visuals'

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
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

  it('honors a backend runtime source-visual rollback after the default-on build starts', () => {
    applyRuntimeFeatures({ sourceVisuals: false })

    renderHook(() => useRecentVisualSources(), { wrapper: createWrapper() })

    expect(sourcesApi.list).not.toHaveBeenCalled()
  })
})
