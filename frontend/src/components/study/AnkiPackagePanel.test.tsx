import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AnkiPackagePanel } from './AnkiPackagePanel'

const uploadPreview = vi.hoisted(() => vi.fn())
const importCards = vi.hoisted(() => vi.fn())
const exportCards = vi.hoisted(() => vi.fn())

vi.mock('@/lib/hooks/use-study-anki', () => ({
  useStudyAnkiImportPreview: () => ({ mutateAsync: uploadPreview, isPending: false, reset: vi.fn() }),
  useStudyAnkiPublish: () => ({ mutateAsync: importCards, isPending: false, reset: vi.fn() }),
  useStudyAnkiExport: () => ({ mutateAsync: exportCards, isPending: false, reset: vi.fn() }),
}))

describe('AnkiPackagePanel', () => {
  beforeEach(() => {
    uploadPreview.mockReset()
    importCards.mockReset()
    exportCards.mockReset()
    uploadPreview.mockResolvedValue({
      schema_version: 1,
      job_id: 'anki_job:one',
      status: 'preview_ready',
      card_count: 2,
      transformed_count: 1,
      skipped_count: 0,
      rejected_count: 1,
      package_sha256: 'a'.repeat(64),
      collection_member: 'collection.anki2',
    })
  })

  it('shows transformed and skipped items before publishing an import', async () => {
    render(<AnkiPackagePanel planId="study_plan:one" />)
    const input = screen.getByLabelText('Anki package')
    const file = new File(['deck'], 'deck.apkg', { type: 'application/octet-stream' })
    fireEvent.change(input, { target: { files: [file] } })

    expect(await screen.findByText('2 cards ready, 1 transformed, 1 rejected')).toBeVisible()
    expect(importCards).not.toHaveBeenCalled()
  })

  it('requires an explicit confirmation before publishing', async () => {
    render(<AnkiPackagePanel planId="study_plan:one" />)
    fireEvent.change(screen.getByLabelText('Anki package'), {
      target: { files: [new File(['deck'], 'deck.apkg')] },
    })
    await screen.findByText('2 cards ready, 1 transformed, 1 rejected')
    fireEvent.click(screen.getByRole('button', { name: 'Import cards' }))
    expect(importCards).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox', { name: /confirm/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Import cards' }))
    await waitFor(() => expect(importCards).toHaveBeenCalledTimes(1))
  })

  it('retries a failed preview with the same selected file', async () => {
    uploadPreview.mockRejectedValueOnce(new Error('temporary')).mockResolvedValueOnce({
      schema_version: 1,
      job_id: 'anki_job:one',
      status: 'preview_ready',
      card_count: 2,
      transformed_count: 1,
      skipped_count: 0,
      rejected_count: 1,
      package_sha256: 'a'.repeat(64),
      collection_member: 'collection.anki2',
    })
    render(<AnkiPackagePanel planId="study_plan:one" />)
    fireEvent.change(screen.getByLabelText('Anki package'), {
      target: { files: [new File(['deck'], 'deck.apkg')] },
    })
    expect(await screen.findByRole('alert')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(uploadPreview).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('2 cards ready, 1 transformed, 1 rejected')).toBeVisible()
  })
})
