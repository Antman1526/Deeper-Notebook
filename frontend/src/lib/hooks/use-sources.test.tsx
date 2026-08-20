/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const toast = vi.fn()

vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast }),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: {
    create: vi.fn(),
    list: vi.fn(),
  },
}))

vi.mock('@/lib/api/source-visuals', () => ({
  sourceVisualsApi: {
    refresh: vi.fn(),
    remove: vi.fn(),
  },
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: () => process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '1',
  isSourceVisualsEnabled: () => process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS === '1',
}))
vi.mock('@/lib/features-client', () => ({
  useSourceVisualsEnabled: () => process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS === '1',
}))

import { sourcesApi } from '@/lib/api/sources'
import { sourceVisualsApi } from '@/lib/api/source-visuals'
import { QUERY_KEYS } from '@/lib/api/query-client'
// v0.8.70 — the helper is exported underscore-prefixed (exported for tests,
// not public API). Alias it so the existing test body reads naturally.
import { _isSourcesListQuery as isSourcesListQuery, useCreateSource } from './use-sources'
import { useRecentVisualSources, useRefreshSourceVisual } from './use-source-visuals'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

function createdSource() {
  return {
    id: 'source:1',
    title: 'Research link',
    asset: null,
    full_text: '',
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: '2026-06-23T00:00:00Z',
    updated: '2026-06-23T00:00:00Z',
  }
}

describe('useCreateSource', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the queued toast when async processing is omitted and defaults on', async () => {
    vi.mocked(sourcesApi.create).mockResolvedValue(createdSource() as any)

    const { result } = renderHook(() => useCreateSource(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        type: 'link',
        url: 'https://example.com/research',
        notebooks: ['notebook:alpha'],
      })
    })

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'sources.sourceQueued',
        description: 'sources.sourceQueuedDesc',
      })
    })
  })

  it('keeps the immediate-add toast when async processing is explicitly disabled', async () => {
    vi.mocked(sourcesApi.create).mockResolvedValue(createdSource() as any)

    const { result } = renderHook(() => useCreateSource(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        type: 'text',
        title: 'Archive note',
        content: 'Keep this source searchable later.',
        notebooks: ['notebook:alpha'],
        async_processing: false,
      })
    })

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'common.success',
        description: 'sources.sourceAddedSuccess',
      })
    })
  })
})

describe('isSourcesListQuery', () => {
  it('matches source list caches without matching source detail or status caches', () => {
    expect(isSourcesListQuery(QUERY_KEYS.sources())).toBe(true)
    expect(isSourcesListQuery(QUERY_KEYS.sources('notebook:alpha'))).toBe(true)
    expect(isSourcesListQuery(QUERY_KEYS.sourcesInfinite('notebook:alpha'))).toBe(true)

    expect(isSourcesListQuery(QUERY_KEYS.source('source:alpha'))).toBe(false)
    expect(isSourcesListQuery(QUERY_KEYS.sourceStatus('source:alpha'))).toBe(false)
  })
})

describe('source visual hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
    delete process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS
  })

  it('reuses one request id across a React Query retry and invalidates exact source-bearing families', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 1, retryDelay: 0 } } })
    const localWrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children)
    const invalidations = vi.spyOn(qc, 'invalidateQueries')
    vi.mocked(sourceVisualsApi.refresh)
      .mockRejectedValueOnce(new Error('transient'))
      .mockResolvedValueOnce({ outcome: 'queued' } as any)

    const { result } = renderHook(() => useRefreshSourceVisual(), { wrapper: localWrapper })
    await act(async () => { await result.current.mutateAsync('source:one') })

    expect(sourceVisualsApi.refresh).toHaveBeenCalledTimes(2)
    expect(vi.mocked(sourceVisualsApi.refresh).mock.calls[0][1]).toBe(vi.mocked(sourceVisualsApi.refresh).mock.calls[1][1])
    expect(invalidations).toHaveBeenCalledWith({ predicate: expect.any(Function) })
    const predicates = invalidations.mock.calls.flatMap((call) => {
      const filters = call[0]
      return filters?.predicate ? [filters.predicate] : []
    })
    expect(predicates.some(predicate => predicate({ queryKey: QUERY_KEYS.sources('notebook:one') } as any))).toBe(true)
    expect(predicates.some(predicate => predicate({ queryKey: QUERY_KEYS.sourcesInfinite('notebook:one') } as any))).toBe(true)
    expect(predicates.some(predicate => predicate({ queryKey: QUERY_KEYS.recentVisualSources(4) } as any))).toBe(true)
    expect(invalidations).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.source('source:one'), exact: true })
    expect(invalidations).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.sourceVisual('source:one'), exact: true })
    expect(invalidations).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.searchSources, exact: true })
    expect(invalidations).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.captureItems, exact: true })
  })

  it('does not automatically retry 4xx mutation failures', async () => {
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: 2, retryDelay: 0 } } })
    const localWrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children)
    vi.mocked(sourceVisualsApi.refresh).mockRejectedValue({ response: { status: 409 } })
    const { result } = renderHook(() => useRefreshSourceVisual(), { wrapper: localWrapper })
    await expect(result.current.mutateAsync('source:one')).rejects.toEqual({ response: { status: 409 } })
    expect(sourceVisualsApi.refresh).toHaveBeenCalledOnce()
  })

  it('bounds recent visual sources to four and enables only when both flags are on', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
    process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '1'
    vi.mocked(sourcesApi.list).mockResolvedValue([])
    renderHook(() => useRecentVisualSources(99), { wrapper })
    expect(sourcesApi.list).toHaveBeenCalledWith({ limit: 4, sort_by: 'updated', sort_order: 'desc' })

    vi.clearAllMocks()
    process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '0'
    renderHook(() => useRecentVisualSources(4), { wrapper })
    expect(sourcesApi.list).not.toHaveBeenCalled()
  })
})
