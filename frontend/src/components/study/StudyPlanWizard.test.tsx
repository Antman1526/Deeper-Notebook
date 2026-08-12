import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StudyPlanWizard } from './StudyPlanWizard'

const createPlan = vi.fn()
const linkSource = vi.fn()
const openSourceDialog = vi.fn()

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
  useAddStudyPlanSource: () => ({ mutateAsync: linkSource, isPending: false }),
}))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => ({ openSourceDialog }),
}))
vi.mock('./StudySourcePicker', () => ({
  StudySourcePicker: ({
    onOpenUpload,
    onLinkSource,
  }: {
    onOpenUpload: (
      onSourceCreated?: (sourceId: string) => void | Promise<void>,
      onSourcesCreated?: (sourceIds: readonly string[]) => void | Promise<void>,
    ) => void
    onLinkSource: (sourceId: string) => void | Promise<void>
  }) => (
    <>
      <div>Source picker</div>
      <button
        type="button"
        onClick={() => onOpenUpload(
          (sourceId) => onLinkSource(sourceId),
          async (sourceIds) => {
            for (const sourceId of sourceIds) await onLinkSource(sourceId)
          },
        )}
      >
        Upload from study wizard
      </button>
    </>
  ),
}))

describe('StudyPlanWizard', () => {
  beforeEach(() => {
    createPlan.mockReset()
    linkSource.mockReset()
    openSourceDialog.mockReset()
  })

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

  it('forwards bounded source IDs from the existing source dialog into plan links', async () => {
    createPlan.mockResolvedValueOnce({
      plan_id: 'study_plan:one',
      goal: 'Understand mechanics',
      starting_level: 'beginner',
    })
    linkSource.mockImplementation(async () => {
      return undefined
    })
    openSourceDialog.mockImplementationOnce((options: {
      onSourcesCreated?: (sourceIds: readonly string[]) => void | Promise<void>
    }) => {
      void options.onSourcesCreated?.(['source:one', 'source:two'])
    })
    render(<StudyPlanWizard open onOpenChange={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Learning goal'), { target: { value: 'Understand mechanics' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Upload from study wizard' }))

    await waitFor(() => {
      expect(openSourceDialog).toHaveBeenCalledWith(expect.objectContaining({ onSourcesCreated: expect.any(Function) }))
      expect(linkSource).toHaveBeenNthCalledWith(1, {
        planId: 'study_plan:one',
        input: { source_id: 'source:one', expected_revision: 1 },
      })
      expect(linkSource).toHaveBeenNthCalledWith(2, {
        planId: 'study_plan:one',
        input: { source_id: 'source:two', expected_revision: 2 },
      })
    })
  })

  it('does not write draft details to browser storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    render(<StudyPlanWizard open onOpenChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Learning goal'), { target: { value: 'Local-only goal' } })
    expect(setItem).not.toHaveBeenCalled()
    setItem.mockRestore()
  })
})
