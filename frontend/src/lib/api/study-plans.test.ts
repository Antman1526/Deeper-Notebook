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

  it('rejects malformed bounded plan collections without exposing payload details', async () => {
    mockGet.mockResolvedValue({
      data: { ...PLAN, source_links: Array.from({ length: 101 }, (_, index) => ({ source_id: `source:${index}` })) },
    } as never)

    await expect(studyPlansApi.get('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
    await expect(studyPlansApi.get('study_plan:one')).rejects.not.toThrow('/private')
  })
})
