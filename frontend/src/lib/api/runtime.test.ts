import { beforeEach, describe, expect, it, vi } from 'vitest'

import apiClient from './client'
import {
  UNKNOWN_RUNTIME_SNAPSHOT,
  normalizeRuntimeSnapshot,
  runtimeApi,
} from './runtime'

vi.mock('./client', () => ({
  default: { get: vi.fn() },
}))

const validSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'ready',
  reasons: [],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: { state: 'ready', stages: [{ stage: 'core_ready', elapsed_ms: 42 }] },
  updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready', ready: 1, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 2, unchanged: 3, failed: 0 },
  backup: { state: 'ready', file_count: 1, newest_age_seconds: 5 },
}

describe('runtimeApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('decodes a valid read-only snapshot', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: validSnapshot } as never)

    await expect(runtimeApi.getSnapshot()).resolves.toEqual(validSnapshot)
    expect(apiClient.get).toHaveBeenCalledWith('/runtime/snapshot')
  })

  it('fails closed to the unknown snapshot for malformed or failed reads', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { status: 'ready', path: '/Users/private', error: 'secret-canary' },
    } as never)

    await expect(runtimeApi.getSnapshot()).resolves.toEqual(UNKNOWN_RUNTIME_SNAPSHOT)
    expect(normalizeRuntimeSnapshot({ error: '/private/token', status: 'ready' })).toEqual(
      UNKNOWN_RUNTIME_SNAPSHOT,
    )

    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('raw transport error'))
    await expect(runtimeApi.getSnapshot()).resolves.toEqual(UNKNOWN_RUNTIME_SNAPSHOT)
  })
})
