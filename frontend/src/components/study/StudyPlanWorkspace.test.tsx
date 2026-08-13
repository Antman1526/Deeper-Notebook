import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanWorkspace } from './StudyPlanWorkspace'

const replace = vi.fn()
const workspaceState = vi.hoisted(() => ({
  activeTab: 'syllabus',
  networkAllowed: true,
  planState: 'approved',
  approvedSyllabusVersion: 2 as number | null,
}))
const workspaceInvoke = vi.hoisted(() => vi.fn())
const progressDecision = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(`tab=${workspaceState.activeTab}`),
  useRouter: () => ({ replace }),
}))
vi.mock('@/lib/hooks/use-study-assistants', () => ({
  useStudyAssistantInvocation: () => ({
    mutateAsync: workspaceInvoke,
    cancel: vi.fn(),
    retry: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
    isCancelled: false,
  }),
}))
vi.mock('@/lib/hooks/use-study-plans', () => ({
  useProposeStudySyllabus: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useStudyPlan: () => ({
    data: {
      plan_id: 'study_plan:one',
      goal: 'Understand mechanics',
      starting_level: 'beginner',
      target_date: null,
      preferences: {
        weekly_minutes: 240,
        session_minutes: 45,
        model_route: workspaceState.networkAllowed ? 'cloud' : 'local',
        network_allowed: workspaceState.networkAllowed,
        approved_network_scope: workspaceState.networkAllowed ? ['https://example.edu/course'] : [],
      },
      source_links: [],
      approved_syllabus_version: workspaceState.approvedSyllabusVersion,
      state: workspaceState.planState,
      version: 4,
      created_at: '2026-08-12T12:00:00Z',
      updated_at: '2026-08-12T12:00:00Z',
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useStudySyllabus: () => ({
    data: {
      plan_id: 'study_plan:one',
      version: 2,
      source_manifest_sha256: 'a'.repeat(64),
      units: [{
        unit_id: 'unit-one',
        title: 'Foundations',
        objectives: ['Understand the basics'],
        prerequisite_unit_ids: [],
        estimated_minutes: 30,
        source_ids: [],
        activities: [],
      }],
      approved_at: null,
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useStudyPlanReadiness: () => ({ data: { ready: true, items: [] }, isLoading: false, isError: false, refetch: vi.fn() }),
  useStudyPlanProgress: () => ({
    data: {
      schema_version: 1,
      concepts: [{ concept_id: 'concept:one', unit_id: 'unit-one', score: 0.65, status: 'developing', attempts: 1, lapses: 0, last_activity_at: '2026-08-12T12:00:00Z' }],
      review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0 },
      proposals: [{ schema_version: 1, proposal_id: 'proposal:extra', concept_id: 'concept:one', unit_id: 'unit-one', action: 'extra_practice', title: 'Add a short practice block', rationale: 'More practice may help.', status: 'proposed', available: true }],
      generated_at: '2026-08-12T12:00:00Z',
      memory_writes: [],
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useDecideStudyProgress: () => ({ mutateAsync: progressDecision, isPending: false }),
}))
vi.mock('./SyllabusEditor', () => ({
  SyllabusEditor: () => <div>Rendered syllabus editor</div>,
}))

describe('StudyPlanWorkspace', () => {
  beforeEach(() => {
    workspaceState.activeTab = 'syllabus'
    workspaceState.networkAllowed = true
    workspaceState.planState = 'approved'
    workspaceState.approvedSyllabusVersion = 2
    workspaceInvoke.mockReset()
    workspaceInvoke.mockResolvedValue(undefined)
    replace.mockReset()
    progressDecision.mockReset()
    progressDecision.mockResolvedValue(undefined)
  })

  it('keeps the selected known tab addressable and falls back unknown values to overview', () => {
    render(<StudyPlanWorkspace planId="study_plan:one" />)

    expect(screen.getByRole('tab', { name: 'Syllabus' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Rendered syllabus editor')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Overview' }))
    expect(replace).toHaveBeenCalledWith('/study/plans/study_plan%3Aone?tab=overview', { scroll: false })
  })

  it('renders loading, empty, error, and retry states without hiding the plan heading', () => {
    render(<StudyPlanWorkspace planId="study_plan:one" />)
    expect(screen.getByRole('heading', { name: 'Understand mechanics', level: 2 })).toBeInTheDocument()
    expect(screen.queryAllByRole('heading', { level: 1 })).toHaveLength(0)
    expect(screen.getByRole('tab', { name: 'Sources' })).toBeInTheDocument()
  })

  it('passes persisted approved scope to Research Gap only when the plan authorizes web access', async () => {
    workspaceState.activeTab = 'learn'
    const { unmount } = render(<StudyPlanWorkspace planId="study_plan:one" />)

    fireEvent.change(screen.getByRole('combobox', { name: 'Tutor mode' }), { target: { value: 'research_gap' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request web research permission' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Find this gap' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask tutor' }))
    await waitFor(() => expect(workspaceInvoke).toHaveBeenCalledWith(expect.objectContaining({
      input: expect.objectContaining({
        network_allowed: true,
        model_route: 'cloud',
        approved_network_scope: ['https://example.edu/course'],
      }),
    })))
    unmount()

    workspaceState.networkAllowed = false
    render(<StudyPlanWorkspace planId="study_plan:one" />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Tutor mode' }), { target: { value: 'research_gap' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request web research permission' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Tutor prompt' }), { target: { value: 'Do not dispatch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask tutor' }))
    expect(workspaceInvoke).toHaveBeenCalledTimes(1)
    expect(screen.getByText('A plan-approved HTTPS scope is required before web research can run.')).toBeInTheDocument()
  })

  it.each(['draft', 'analyzing_sources', 'syllabus_proposed', 'editing', 'archived'] as const)(
    'keeps Tutor unavailable for the %s plan lifecycle without an approved syllabus',
    (planState) => {
      workspaceState.activeTab = 'learn'
      workspaceState.planState = planState
      workspaceState.approvedSyllabusVersion = null

      render(<StudyPlanWorkspace planId="study_plan:one" />)

      expect(screen.getByRole('status')).toHaveTextContent(/Tutor unavailable|approved syllabus/i)
      expect(screen.queryByRole('combobox', { name: 'Tutor mode' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Ask tutor' })).not.toBeInTheDocument()
      expect(workspaceInvoke).not.toHaveBeenCalled()
    },
  )

  it('mounts progress and sends one stable request with the current revision on Accept', async () => {
    workspaceState.activeTab = 'progress'
    render(<StudyPlanWorkspace planId="study_plan:one" />)

    fireEvent.click(screen.getByRole('button', { name: 'Accept Add a short practice block' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(progressDecision).toHaveBeenCalledWith({
      planId: 'study_plan:one',
      input: expect.objectContaining({
        proposal_id: 'proposal:extra',
        decision: 'accepted',
        expected_revision: 4,
        request_id: expect.stringMatching(/^study-decision:/),
      }),
    }))
  })
})
