// v0.8.130 — mutations that send an idempotency key in their variables (the same key
// on every attempt) repeat a lost request once; the default policy never repeats a POST.

import { act, renderHook } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/study-anki', () => ({ studyAnkiApi: { publish: vi.fn() } }))
vi.mock('@/lib/api/study-plans', () => ({ studyPlansApi: { decideProgress: vi.fn() } }))

import { createQueryClient } from '@/lib/api/query-client'
import { studyAnkiApi } from '@/lib/api/study-anki'
import { studyPlansApi } from '@/lib/api/study-plans'
import { useStudyAnkiPublish } from './use-study-anki'
import { useDecideStudyProgress } from './use-study-plans'

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = React.useMemo(() => {
    const qc = createQueryClient()
    qc.setDefaultOptions({ ...qc.getDefaultOptions(), mutations: { ...qc.getDefaultOptions().mutations, retryDelay: 0 } })
    return qc
  }, [])
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const lost = () => Object.assign(new Error('Network Error'), { config: { method: 'post' } })

describe('idempotency-keyed mutations', () => {
  it('Anki publish repeats a lost request once, with the same request id', async () => {
    vi.mocked(studyAnkiApi.publish).mockRejectedValueOnce(lost()).mockResolvedValueOnce({} as never)
    const { result } = renderHook(() => useStudyAnkiPublish(), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ planId: 'plan:1', jobId: 'job:1', requestId: 'req-1' })
    })

    expect(vi.mocked(studyAnkiApi.publish).mock.calls.map((call) => call[2])).toEqual(['req-1', 'req-1'])
  })

  it('a study progress decision repeats a lost request once, with the same request id', async () => {
    vi.mocked(studyPlansApi.decideProgress).mockRejectedValueOnce(lost()).mockResolvedValueOnce({ projection: {} } as never)
    const { result } = renderHook(() => useDecideStudyProgress(), { wrapper: Wrapper })
    const input = { request_id: 'req-2' } as never

    await act(async () => {
      await result.current.mutateAsync({ planId: 'plan:1', input })
    })

    expect(vi.mocked(studyPlansApi.decideProgress)).toHaveBeenCalledTimes(2)
  })
})
