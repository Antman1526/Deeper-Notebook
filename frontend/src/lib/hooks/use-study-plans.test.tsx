import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { studyPlansApi } from '@/lib/api/study-plans'
import {
  useApproveStudySyllabus,
  useProposeStudySyllabus,
  useSaveStudySyllabus,
  useStudyPlan,
  useStudyPlanProgress,
  useStudyPlanReadiness,
  useStudySyllabus,
  useDecideStudyProgress,
} from './use-study-plans'

vi.mock('@/lib/api/study-plans', () => ({
  studyPlansApi: {
    get: vi.fn(),
    syllabus: vi.fn(),
    readiness: vi.fn(),
    proposeSyllabus: vi.fn(),
    saveSyllabus: vi.fn(),
    approveSyllabus: vi.fn(),
    progress: vi.fn(),
    decideProgress: vi.fn(),
  },
}))

const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
function Wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('study plan workspace hooks', () => {
  it('owns typed plan, syllabus, readiness, and lifecycle calls with targeted invalidation', async () => {
    vi.mocked(studyPlansApi.get).mockResolvedValue({ plan_id: 'study_plan:one' } as never)
    vi.mocked(studyPlansApi.syllabus).mockResolvedValue({ plan_id: 'study_plan:one', version: 2 } as never)
    vi.mocked(studyPlansApi.readiness).mockResolvedValue({ ready: true, items: [] } as never)
    vi.mocked(studyPlansApi.progress).mockResolvedValue({
      schema_version: 1,
      concepts: [],
      review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0 },
      proposals: [],
      generated_at: '2026-08-12T12:00:00Z',
      memory_writes: [],
    } as never)
    vi.mocked(studyPlansApi.proposeSyllabus).mockResolvedValue({ plan_id: 'study_plan:one', version: 2 } as never)
    vi.mocked(studyPlansApi.saveSyllabus).mockResolvedValue({ plan_id: 'study_plan:one', version: 3 } as never)
    vi.mocked(studyPlansApi.approveSyllabus).mockResolvedValue({ plan_id: 'study_plan:one', version: 5 } as never)

    const plan = renderHook(() => useStudyPlan('study_plan:one'), { wrapper: Wrapper })
    const syllabus = renderHook(() => useStudySyllabus('study_plan:one', 2), { wrapper: Wrapper })
    const readiness = renderHook(() => useStudyPlanReadiness('study_plan:one'), { wrapper: Wrapper })
    const progress = renderHook(() => useStudyPlanProgress('study_plan:one'), { wrapper: Wrapper })
    await waitFor(() => expect(plan.result.current.data).toBeDefined())
    await waitFor(() => expect(syllabus.result.current.data).toBeDefined())
    await waitFor(() => expect(readiness.result.current.data).toBeDefined())
    await waitFor(() => expect(progress.result.current.data).toBeDefined())

    const propose = renderHook(() => useProposeStudySyllabus(), { wrapper: Wrapper })
    const save = renderHook(() => useSaveStudySyllabus(), { wrapper: Wrapper })
    const approve = renderHook(() => useApproveStudySyllabus(), { wrapper: Wrapper })
    const decide = renderHook(() => useDecideStudyProgress(), { wrapper: Wrapper })
    await propose.result.current.mutateAsync({ planId: 'study_plan:one', input: { expected_revision: 4 } })
    await save.result.current.mutateAsync({
      planId: 'study_plan:one',
      input: { expected_revision: 4, version: 3, source_manifest_sha256: 'a'.repeat(64), units: [] },
    })
    await approve.result.current.mutateAsync({
      planId: 'study_plan:one',
      input: { syllabus_version: 3, expected_revision: 5 },
    })
    vi.mocked(studyPlansApi.decideProgress).mockResolvedValue({ proposal_id: 'proposal:one', decision: 'dismissed', projection: progress.result.current.data } as never)
    await decide.result.current.mutateAsync({ planId: 'study_plan:one', input: { proposal_id: 'proposal:one', decision: 'dismissed', request_id: 'decision:one' } })

    expect(studyPlansApi.get).toHaveBeenCalledWith('study_plan:one')
    expect(studyPlansApi.syllabus).toHaveBeenCalledWith('study_plan:one', 2)
    expect(studyPlansApi.readiness).toHaveBeenCalledWith('study_plan:one')
    expect(studyPlansApi.progress).toHaveBeenCalledWith('study_plan:one')
    expect(studyPlansApi.decideProgress).toHaveBeenCalledWith('study_plan:one', { proposal_id: 'proposal:one', decision: 'dismissed', request_id: 'decision:one' })
    expect(studyPlansApi.proposeSyllabus).toHaveBeenCalledWith('study_plan:one', { expected_revision: 4 })
    expect(studyPlansApi.saveSyllabus).toHaveBeenCalledWith('study_plan:one', expect.objectContaining({ version: 3 }))
    expect(studyPlansApi.approveSyllabus).toHaveBeenCalledWith('study_plan:one', { syllabus_version: 3, expected_revision: 5 })
  })

  it('treats a missing syllabus as an empty proposal state without hiding service errors', async () => {
    vi.mocked(studyPlansApi.syllabus).mockRejectedValueOnce({ response: { status: 404 } })
    const missing = renderHook(() => useStudySyllabus('study_plan:missing'), { wrapper: Wrapper })
    await waitFor(() => expect(missing.result.current.isFetched).toBe(true))
    expect(missing.result.current.data).toBeNull()
    expect(missing.result.current.isError).toBe(false)
  })
})
