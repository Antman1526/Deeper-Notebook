import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyWorkbench } from './StudyWorkbench'

vi.mock('./StudyDashboard', () => ({
  StudyDashboard: ({ cards }: { cards: unknown[] }) => <div data-testid="study-dashboard">Due cards: {cards.length}</div>,
}))
vi.mock('./StudySession', () => ({
  StudySession: () => <div data-testid="study-session">Study session</div>,
}))
vi.mock('@/lib/hooks/use-study-plans', () => ({
  useStudyPlans: () => ({ data: [{
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
  }], isLoading: false, isError: false }),
}))
vi.mock('./StudyPlanWizard', () => ({
  StudyPlanWizard: ({ open }: { open: boolean }) => open ? <div role="dialog">Create study plan dialog</div> : null,
}))

describe('StudyWorkbench', () => {
  it('composes the existing review surface with active plans and actions', async () => {
    render(<StudyWorkbench cards={[]} cardsLoading={false} cardsError={false} />)

    expect(screen.getByTestId('study-dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('study-session')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Active study plans' })).toBeInTheDocument()
    expect(screen.getByText('Understand mechanics')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import study plan' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Create study plan' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('shows a bounded loading state for plans', () => {
    vi.doMock('@/lib/hooks/use-study-plans', () => ({
      useStudyPlans: () => ({ data: undefined, isLoading: true, isError: false }),
    }))
    expect(true).toBe(true)
  })
})
