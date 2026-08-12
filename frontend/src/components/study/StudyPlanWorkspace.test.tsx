import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyPlanWorkspace } from './StudyPlanWorkspace'

const replace = vi.fn()

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('tab=syllabus'),
  useRouter: () => ({ replace }),
}))
vi.mock('@/lib/hooks/use-study-plans', () => ({
  useProposeStudySyllabus: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useStudyPlan: () => ({
    data: {
      plan_id: 'study_plan:one',
      goal: 'Understand mechanics',
      starting_level: 'beginner',
      target_date: null,
      preferences: null,
      source_links: [],
      approved_syllabus_version: null,
      state: 'editing',
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
}))
vi.mock('./SyllabusEditor', () => ({
  SyllabusEditor: () => <div>Rendered syllabus editor</div>,
}))

describe('StudyPlanWorkspace', () => {
  it('keeps the selected known tab addressable and falls back unknown values to overview', () => {
    render(<StudyPlanWorkspace planId="study_plan:one" />)

    expect(screen.getByRole('tab', { name: 'Syllabus' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Rendered syllabus editor')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Overview' }))
    expect(replace).toHaveBeenCalledWith('/study/plans/study_plan%3Aone?tab=overview', { scroll: false })
  })

  it('renders loading, empty, error, and retry states without hiding the plan heading', () => {
    render(<StudyPlanWorkspace planId="study_plan:one" />)
    expect(screen.getByRole('heading', { name: 'Understand mechanics' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Sources' })).toBeInTheDocument()
  })
})
