import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudyProgressPanel } from './StudyProgressPanel'
import { decodeStudyMasteryProjection } from '@/lib/types/study-progress'

const projection = {
  schema_version: 1 as const,
  concepts: [
    {
      concept_id: 'concept:one',
      unit_id: 'unit:one',
      score: 0.32,
      status: 'needs_review' as const,
      attempts: 2,
      last_activity_at: '2026-08-12T12:00:00Z',
      lapses: 1,
    },
  ],
  review_consistency: {
    reviews: 1,
    lapses: 1,
    due_reviews: 1,
    on_time_rate: 0,
  },
  proposals: [
    {
      schema_version: 1 as const,
      proposal_id: 'proposal:one',
      concept_id: 'concept:one',
      unit_id: 'unit:one',
      action: 'prerequisite_detour' as const,
      title: 'Review the prerequisite first',
      rationale: 'A prerequisite concept is still weak.',
      status: 'proposed' as const,
      available: true,
    },
  ],
  generated_at: '2026-08-12T12:00:00Z',
  memory_writes: [],
}

describe('StudyProgressPanel', () => {
  it('renders loading, empty, and error states', () => {
    const { rerender } = render(<StudyProgressPanel state="loading" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading study progress')

    rerender(<StudyProgressPanel state="empty" />)
    expect(screen.getByText('No study progress yet.')).toBeVisible()

    rerender(<StudyProgressPanel state="error" onRetry={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Study progress could not be loaded')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
  })

  it('requires explicit confirmation before accepting a proposal', () => {
    const onAccept = vi.fn()
    render(<StudyProgressPanel state="ready" projection={projection} onAccept={onAccept} />)

    const accept = screen.getByRole('button', { name: 'Accept Review the prerequisite first' })
    expect(onAccept).not.toHaveBeenCalled()
    fireEvent.click(accept)
    expect(onAccept).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(onAccept).toHaveBeenCalledWith('proposal:one', expect.stringMatching(/^study-decision:/))
  })

  it('renders unavailable proposals without a mutation control', () => {
    render(
      <StudyProgressPanel
        state="ready"
        projection={{
          ...projection,
          proposals: [{ ...projection.proposals[0], available: false }],
        }}
      />,
    )

    expect(screen.getByText('This adaptation is unavailable.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument()
  })

  it('fails closed when an available proposal has no decision handlers', () => {
    render(<StudyProgressPanel state="ready" projection={projection} />)

    expect(screen.getByText('This adaptation is unavailable.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument()
  })

  it('confirms a dismissal and rejects malformed projection data', () => {
    const onDismiss = vi.fn()
    render(<StudyProgressPanel state="ready" projection={projection} onDismiss={onDismiss} />)

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Review the prerequisite first' }))
    expect(onDismiss).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(onDismiss).toHaveBeenCalledWith('proposal:one', expect.stringMatching(/^study-decision:/))

    expect(() => decodeStudyMasteryProjection({ ...projection, proposals: [{ ...projection.proposals[0], unexpected: true }] })).toThrow('Invalid Study progress response')
    expect(() => decodeStudyMasteryProjection({ ...projection, review_consistency: { ...projection.review_consistency, extra: true } })).toThrow('Invalid Study progress response')
    expect(() => decodeStudyMasteryProjection({ ...projection, generated_at: '2026-08-12T12:00:00' })).toThrow('Invalid Study progress response')
    expect(() => decodeStudyMasteryProjection({ ...projection, concepts: [{ ...projection.concepts[0], lapses: -1 }] })).toThrow('Invalid Study progress response')
  })

  it('renders decoder failures as a retryable error instead of empty progress', () => {
    const onRetry = vi.fn()
    render(<StudyProgressPanel state="ready" projection={{ ...projection, generated_at: '2026-08-12T12:00:00' } as never} onRetry={onRetry} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Study progress could not be read')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('keeps the confirmation open and offers retry when a decision fails', async () => {
    const onDismiss = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
    render(<StudyProgressPanel state="ready" projection={projection} onDismiss={onDismiss} />)

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Review the prerequisite first' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled()
    expect(screen.getByRole('dialog')).toBeVisible()
    const firstRequestId = onDismiss.mock.calls[0][1]
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(2))
    expect(onDismiss.mock.calls[1][1]).toBe(firstRequestId)
  })
})
