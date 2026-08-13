import { describe, expect, it, vi, beforeEach } from 'vitest'

import apiClient from './client'
import { studyPlansApi } from './study-plans'

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    put: vi.fn(),
  },
}))

const mockGet = vi.mocked(apiClient.get)
const mockPost = vi.mocked(apiClient.post)

const PLAN = {
  plan_id: 'study_plan:one',
  goal: 'Understand mechanics',
  starting_level: 'beginner',
  target_date: null,
  preferences: null,
  source_links: [],
  approved_syllabus_version: null,
  state: 'draft',
  version: 1,
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z',
} as const

describe('studyPlansApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fails closed on a plan response with extra secret fields', async () => {
    mockGet.mockResolvedValue({ data: { ...PLAN, absolute_path: '/private/source.pdf' } } as never)

    await expect(studyPlansApi.get('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
  })

  it('uses typed plan endpoints and decodes the response', async () => {
    mockGet.mockImplementation(async (url) => ({ data: url === '/study/plans' ? [PLAN] : PLAN }) as never)
    mockPost.mockResolvedValue({ data: PLAN } as never)

    await expect(studyPlansApi.get('study_plan:one')).resolves.toEqual(PLAN)
    await expect(studyPlansApi.list()).resolves.toEqual([PLAN])
    await expect(studyPlansApi.create({ goal: PLAN.goal, starting_level: PLAN.starting_level })).resolves.toEqual(PLAN)
    expect(mockGet).toHaveBeenCalledWith('/study/plans/study_plan%3Aone')
    expect(mockPost).toHaveBeenCalledWith('/study/plans', {
      goal: PLAN.goal,
      starting_level: PLAN.starting_level,
    })
  })

  it('treats a product-compatible empty syllabus response as no proposal', async () => {
    mockGet.mockResolvedValue({ data: undefined, status: 204 } as never)

    await expect(studyPlansApi.syllabus('study_plan:one')).resolves.toBeNull()
  })

  it('still rejects an empty 200 syllabus payload', async () => {
    mockGet.mockResolvedValue({ data: undefined, status: 200 } as never)

    await expect(studyPlansApi.syllabus('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
  })

  it('projects persisted model and approved web scope preferences', async () => {
    const persistedPlan = {
      ...PLAN,
      preferences: {
        weekly_minutes: 240,
        session_minutes: 45,
        model_route: 'cloud' as const,
        network_allowed: true,
        approved_network_scope: ['https://example.edu/course'],
      },
    }
    mockGet.mockResolvedValue({ data: persistedPlan } as never)

    await expect(studyPlansApi.get('study_plan:one')).resolves.toEqual(persistedPlan)
  })

  it('fails closed on an impossible persisted network preference', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...PLAN,
        preferences: {
          weekly_minutes: 240,
          session_minutes: 45,
          model_route: 'local',
          network_allowed: false,
          approved_network_scope: ['https://example.edu/course'],
        },
      },
    } as never)

    await expect(studyPlansApi.get('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
  })

  it('rejects malformed bounded plan collections without exposing payload details', async () => {
    mockGet.mockResolvedValue({
      data: { ...PLAN, source_links: Array.from({ length: 101 }, (_, index) => ({ source_id: `source:${index}` })) },
    } as never)

    await expect(studyPlansApi.get('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
    await expect(studyPlansApi.get('study_plan:one')).rejects.not.toThrow('/private')
  })

  it('rejects malformed runtime request values before touching the client', async () => {
    await expect(studyPlansApi.create({
      goal: undefined as never,
      starting_level: 'beginner',
    })).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.get(undefined as never)).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.update('study_plan:one', {
      expected_revision: 1,
      goal: 42 as never,
    })).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.addSource('study_plan:one', {
      source_id: undefined as never,
      expected_revision: 1,
    })).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.removeSource('study_plan:one', {
      source_id: 'source:one',
      expected_revision: '1' as never,
    })).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.readiness(undefined as never)).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.proposeSyllabus('study_plan:one', undefined as never)).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.saveSyllabus('study_plan:one', {
      expected_revision: 1,
      version: 1,
      source_manifest_sha256: undefined as never,
      units: [],
    })).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.approveSyllabus('study_plan:one', {
      syllabus_version: 1,
      expected_revision: undefined as never,
    })).rejects.toThrow('Invalid Study Plan request')
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('rejects extra and oversized request fields without dispatching', async () => {
    await expect(studyPlansApi.create({
      goal: 'Understand mechanics',
      starting_level: 'beginner',
      secret: 'nope',
    } as never)).rejects.toThrow('Invalid Study Plan request')
    await expect(studyPlansApi.get(`study_plan:${'x'.repeat(513)}`)).rejects.toThrow('Invalid Study Plan request')
    expect(mockGet).not.toHaveBeenCalled()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('loads bounded mastery progress and posts an explicit decision', async () => {
    const progress = {
      schema_version: 1,
      concepts: [],
      review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0 },
      proposals: [],
      generated_at: '2026-08-12T12:00:00Z',
      memory_writes: [],
    }
    mockGet.mockResolvedValue({ data: progress } as never)
    mockPost.mockResolvedValue({ data: { proposal_id: 'proposal:one', decision: 'dismissed', projection: progress } } as never)

    await expect(studyPlansApi.progress('study_plan:one')).resolves.toEqual(progress)
    await expect(studyPlansApi.decideProgress('study_plan:one', {
      proposal_id: 'proposal:one',
      decision: 'dismissed',
      request_id: 'decision:one',
    })).resolves.toMatchObject({ proposal_id: 'proposal:one', decision: 'dismissed' })
    expect(mockGet).toHaveBeenCalledWith('/study/plans/study_plan%3Aone/progress')
    expect(mockPost).toHaveBeenCalledWith('/study/plans/study_plan%3Aone/progress:decision', {
      proposal_id: 'proposal:one',
      decision: 'dismissed',
      request_id: 'decision:one',
    })
  })

  it('rejects malformed progress decisions before dispatch', async () => {
    await expect(studyPlansApi.decideProgress('study_plan:one', {
      proposal_id: 'proposal:one',
      decision: 'accepted',
      request_id: 'decision:one',
    } as never)).rejects.toThrow('Invalid Study progress request')
    expect(mockPost).not.toHaveBeenCalled()
  })
})
