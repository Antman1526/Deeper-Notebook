import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { evaluationsApi } from '@/lib/api/evaluations'
import {
  evaluationPersistencePendingKey,
  markEvaluationPersistencePending,
  useLatestMessageEvaluations,
} from './use-evaluation'

vi.mock('@/lib/api/evaluations', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/evaluations')>('@/lib/api/evaluations')
  return { ...actual, evaluationsApi: { ...actual.evaluationsApi, latestBatch: vi.fn() } }
})

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

function wrapperFor(client: QueryClient) {
  return function QueryWrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

describe('useLatestMessageEvaluations', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetches all visible notebook messages through one deduplicated batch', async () => {
    vi.mocked(evaluationsApi.latestBatch).mockResolvedValueOnce({
      'message:one': {
        run: {
          id: 'evaluation_run:one',
          notebook_id: 'notebook:one',
          message_id: 'message:one',
          evaluator_version: 'deterministic-v1',
          metrics: {},
        },
        status: 'completed',
        counts: { supported: 1, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
        verdicts: [],
      },
    })

    const { result } = renderHook(
      () => useLatestMessageEvaluations('notebook:one', [
        'message:one',
        'message:one',
        'message:two',
      ]),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data?.['message:one']).toBeDefined())
    expect(evaluationsApi.latestBatch).toHaveBeenCalledTimes(1)
    expect(evaluationsApi.latestBatch).toHaveBeenCalledWith(
      'notebook:one',
      ['message:one', 'message:two'],
    )
  })

  it('does not request Source Chat or an empty notebook message list', () => {
    const { result } = renderHook(
      () => useLatestMessageEvaluations(undefined, []),
      { wrapper },
    )

    expect(result.current.fetchStatus).toBe('idle')
    expect(evaluationsApi.latestBatch).not.toHaveBeenCalled()
  })

  it('polls pending evaluations every 1.5s, then stops after completion', async () => {
    vi.mocked(evaluationsApi.latestBatch)
      .mockResolvedValueOnce({
        'message:one': {
          run: {
            id: 'evaluation_run:one',
            notebook_id: 'notebook:one',
            message_id: 'message:one',
            evaluator_version: 'deterministic-v1',
            metrics: {},
          },
          status: 'running',
          counts: { supported: 0, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
          verdicts: [],
        },
      })
      .mockResolvedValueOnce({
        'message:one': {
          run: {
            id: 'evaluation_run:one',
            notebook_id: 'notebook:one',
            message_id: 'message:one',
            evaluator_version: 'deterministic-v1',
            metrics: {},
          },
          status: 'completed',
          counts: { supported: 1, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
          verdicts: [],
        },
      })

    const { result } = renderHook(
      () => useLatestMessageEvaluations('notebook:one', ['message:one']),
      { wrapper },
    )
    await waitFor(() => {
      expect(result.current.data?.['message:one']?.status).toBe('running')
    })
    expect(evaluationsApi.latestBatch).toHaveBeenCalledTimes(1)

    await new Promise((resolve) => setTimeout(resolve, 1_650))
    await waitFor(() => {
      expect(evaluationsApi.latestBatch).toHaveBeenCalledTimes(2)
      expect(result.current.data?.['message:one']?.status).toBe('completed')
    })

    await new Promise((resolve) => setTimeout(resolve, 1_650))
    expect(evaluationsApi.latestBatch).toHaveBeenCalledTimes(2)
  })

  it('retries an empty lookup while a newly completed chat evaluation is persisting', async () => {
    const client = new QueryClient()
    markEvaluationPersistencePending(
      client,
      'notebook:one',
      'message:one',
    )
    vi.mocked(evaluationsApi.latestBatch)
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({
        'message:one': {
          run: {
            id: 'evaluation_run:one',
            notebook_id: 'notebook:one',
            message_id: 'message:one',
            evaluator_version: 'deterministic-v1',
            metrics: {},
          },
          status: 'completed',
          counts: { supported: 1, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
          verdicts: [],
        },
      })

    const { result } = renderHook(
      () => useLatestMessageEvaluations('notebook:one', ['message:one']),
      { wrapper: wrapperFor(client) },
    )

    await waitFor(() => expect(result.current.data).toEqual({}))
    expect(evaluationsApi.latestBatch).toHaveBeenCalledTimes(1)
    await new Promise((resolve) => setTimeout(resolve, 1_650))
    await waitFor(() => {
      expect(result.current.data?.['message:one']?.status).toBe('completed')
    })
    expect(client.getQueryData(
      evaluationPersistencePendingKey('notebook:one', 'message:one'),
    )).toBeUndefined()
  })
})
