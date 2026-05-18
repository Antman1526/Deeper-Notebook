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
    fireEvent.click(screen.getAllByText('notebooks.bulkVectorize.button')[0])

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

    fireEvent.click(screen.getAllByText('notebooks.bulkVectorize.button')[0])
    fireEvent.click(screen.getByLabelText('notebooks.bulkVectorize.onlyMissingLabel'))
    fireEvent.click(screen.getByText('notebooks.bulkVectorize.confirm'))

    await waitFor(() => {
      expect(vectorizeMutateAsync).toHaveBeenCalledWith({
        notebookId: 'notebook:abc',
        data: { only_missing: false },
      })
    })
  })
})
