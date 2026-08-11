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

  it('projects a valid snapshot without retaining hostile fields at any level', () => {
    const hostileSnapshot = {
      ...validSnapshot,
      error: 'secret-canary',
      path: '/Users/private/runtime',
      readiness: { ...validSnapshot.readiness, details: 'database://user:token@private' },
      startup: {
        ...validSnapshot.startup,
        stack: 'stack-canary',
        stages: [{ ...validSnapshot.startup.stages[0], file: '/private/startup.log' }],
      },
      updates: { ...validSnapshot.updates, release_url: 'https://token@example.test/release' },
      vault: { ...validSnapshot.vault, root: '/Volumes/private-vault' },
      knowledge: { ...validSnapshot.knowledge, source_text: 'private-source-canary' },
      backup: { ...validSnapshot.backup, directory: '/private/backups' },
    }

    const projected = normalizeRuntimeSnapshot(hostileSnapshot)

    expect(projected).toEqual(validSnapshot)
    expect(projected).not.toBe(hostileSnapshot)
    expect(JSON.stringify(projected)).not.toMatch(/secret-canary|private|token|stack-canary/i)
  })

  it('deduplicates a bounded allowlisted reason list', () => {
    expect(normalizeRuntimeSnapshot({
      ...validSnapshot,
      reasons: ['database_offline', 'database_offline', 'migrations_pending'],
    }).reasons).toEqual(['database_offline', 'migrations_pending'])
  })

  it.each([
    ['an oversized reason list', { ...validSnapshot, reasons: Array(16).fill('readiness_unknown') }],
    [
      'an oversized startup stage list',
      {
        ...validSnapshot,
        startup: {
          ...validSnapshot.startup,
          stages: Array.from({ length: 17 }, () => ({ stage: 'core_ready', elapsed_ms: 42 })),
        },
      },
    ],
    ['an unknown reason code', { ...validSnapshot, reasons: ['untrusted_provider_error'] }],
  ])('fails closed for %s', (_label, snapshot) => {
    expect(normalizeRuntimeSnapshot(snapshot)).toEqual(UNKNOWN_RUNTIME_SNAPSHOT)
  })
})
