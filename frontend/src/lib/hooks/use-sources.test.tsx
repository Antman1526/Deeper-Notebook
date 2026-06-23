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
  },
}))

import { sourcesApi } from '@/lib/api/sources'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { isSourcesListQuery, useCreateSource } from './use-sources'

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
