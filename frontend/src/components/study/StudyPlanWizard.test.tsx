import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyPlanWizard } from './StudyPlanWizard'

const createPlan = vi.fn()

vi.mock('@/lib/hooks/use-study-plans', () => ({
  useCreateStudyPlan: () => ({ mutateAsync: createPlan, isPending: false, error: null }),
  useStudyPlan: (planId: string | null) => ({
    data: planId ? {
      plan_id: planId,
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
    } : null,
    isLoading: false,
    isError: false,
  }),
  useAddStudyPlanSource: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('./StudySourcePicker', () => ({
  StudySourcePicker: () => <div>Source picker</div>,
}))

describe('StudyPlanWizard', () => {
  it('saves a resumable draft before source selection', async () => {
    createPlan.mockResolvedValueOnce({
      plan_id: 'study_plan:one',
      goal: 'Understand mechanics',
      starting_level: 'beginner',
    })
    render(<StudyPlanWizard open onOpenChange={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Learning goal'), { target: { value: 'Understand mechanics' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

    expect(createPlan).toHaveBeenCalledWith(expect.objectContaining({
      goal: 'Understand mechanics',
    }))
    expect(await screen.findByText('Source picker')).toBeInTheDocument()
  })

  it('does not write draft details to browser storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    render(<StudyPlanWizard open onOpenChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Learning goal'), { target: { value: 'Local-only goal' } })
    expect(setItem).not.toHaveBeenCalled()
    setItem.mockRestore()
  })
})
