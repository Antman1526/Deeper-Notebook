import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { runtimeApi, type RuntimeSnapshot } from '@/lib/api/runtime'

import { RUNTIME_SNAPSHOT_QUERY_KEY, useRuntimeSnapshot } from './use-runtime-snapshot'

vi.mock('@/lib/api/runtime', () => ({
  runtimeApi: { getSnapshot: vi.fn() },
}))

const snapshot: RuntimeSnapshot = {
  schema_version: 'runtime-snapshot-v1' as const,
  status: 'ready' as const,
  reasons: [],
  readiness: { state: 'ready' as const, database: 'online' as const, migrations: 'applied' as const },
  startup: { state: 'ready' as const, stages: [] },
  updates: { state: 'ready' as const, enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready' as const, ready: 0, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready' as const, projected: 0, unchanged: 0, failed: 0 },
  backup: { state: 'unknown' as const, file_count: 0, newest_age_seconds: null },
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client }, children)
}

describe('useRuntimeSnapshot', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shares one cached query between Horizon and Settings consumers', async () => {
    vi.mocked(runtimeApi.getSnapshot).mockResolvedValue(snapshot)

    const { result } = renderHook(
      () => [useRuntimeSnapshot(), useRuntimeSnapshot()] as const,
      { wrapper },
    )

    await waitFor(() => expect(result.current[0].data?.status).toBe('ready'))

    expect(runtimeApi.getSnapshot).toHaveBeenCalledOnce()
    expect(RUNTIME_SNAPSHOT_QUERY_KEY).toEqual(['runtime', 'snapshot'])
  })
})
