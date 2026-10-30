// v0.7.119 — Confirms the bulk-vectorize confirm dialog submits the
// expected body to /notebooks/{id}/vectorize_sources and surfaces the
// warnings array.
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { BulkVectorizeButton } from './BulkVectorizeButton'

const vectorizeMutateAsync = vi.fn()

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useVectorizeNotebookSources: () => ({
    mutateAsync: vectorizeMutateAsync,
    isPending: false,
  }),
}))

describe('BulkVectorizeButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vectorizeMutateAsync.mockReset()
  })

  it('invokes vectorize with { only_missing: true } by default', async () => {
    vectorizeMutateAsync.mockResolvedValueOnce({
      notebook_id: 'notebook:abc',
      notebook_name: 'Test',
      total_sources: 3,
      queued: 2,
      skipped: 1,
      failed: 0,
      sources: [],
      warnings: [],
    })

    render(<BulkVectorizeButton notebookId="notebook:abc" />)

    // Open the dialog.
    fireEvent.click(screen.getByRole('button', { name: 'notebooks.bulkVectorize.button' })) // v0.8.130 — icon-only trigger, same accessible name

    // Default checkbox state should be true (label is present).
    expect(
      screen.getByLabelText('notebooks.bulkVectorize.onlyMissingLabel'),
    ).toBeChecked()

    fireEvent.click(screen.getByText('notebooks.bulkVectorize.confirm'))

    await waitFor(() => {
      expect(vectorizeMutateAsync).toHaveBeenCalledWith({
        notebookId: 'notebook:abc',
        data: { only_missing: true },
      })
    })
  })

  it('flips only_missing to false when the user unchecks', async () => {
    vectorizeMutateAsync.mockResolvedValueOnce({
      notebook_id: 'notebook:abc',
      notebook_name: 'Test',
      total_sources: 1,
      queued: 1,
      skipped: 0,
      failed: 0,
      sources: [],
      warnings: [],
    })

    render(<BulkVectorizeButton notebookId="notebook:abc" />)

    fireEvent.click(screen.getByRole('button', { name: 'notebooks.bulkVectorize.button' })) // v0.8.130 — icon-only trigger, same accessible name
    fireEvent.click(screen.getByLabelText('notebooks.bulkVectorize.onlyMissingLabel'))
    fireEvent.click(screen.getByText('notebooks.bulkVectorize.confirm'))

    await waitFor(() => {
      expect(vectorizeMutateAsync).toHaveBeenCalledWith({
        notebookId: 'notebook:abc',
        data: { only_missing: false },
      })
    })
  })

  // v0.8.130 — Phase 2b: the Sources "Source options" menu opens this dialog
  // itself, so the component must support a controlled, trigger-less mode.
  it('renders no trigger and follows the controlled open prop when hideTrigger is set', () => {
    const onOpenChange = vi.fn()
    const { rerender } = render(
      <BulkVectorizeButton notebookId="notebook:abc" open={false} onOpenChange={onOpenChange} hideTrigger />,
    )
    expect(screen.queryByRole('button', { name: 'notebooks.bulkVectorize.button' })).toBeNull()
    expect(screen.queryByText('notebooks.bulkVectorize.title')).toBeNull()

    rerender(
      <BulkVectorizeButton notebookId="notebook:abc" open onOpenChange={onOpenChange} hideTrigger />,
    )
    expect(screen.getByText('notebooks.bulkVectorize.title')).toBeTruthy()

    fireEvent.click(screen.getByText('filesystem.cancel'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
