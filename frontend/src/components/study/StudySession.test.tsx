import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StudySession } from './StudySession'

const mutateAsync = vi.fn()

vi.mock('@/lib/hooks/use-study', () => ({
  useReviewStudyCard: () => ({ mutateAsync, isPending: false }),
}))

describe('StudySession', () => {
  beforeEach(() => vi.clearAllMocks())

  it('requires an answer reveal before a source-grounded rating', async () => {
    render(<StudySession cards={[{
      id: 'study_card:one', artifact_id: 'artifact:one', artifact_card_id: 'one', version: 1,
      front: 'What is the local-first principle?', back: 'Keep source data on this device.',
      citations: [{ source_id: 'source:one', source_content_sha256: 'a'.repeat(64), start: 0, end: 12 }],
      due: '2026-07-17T00:00:00Z', stability: null, difficulty: null, lapse_count: 0, current: true,
    }]} />)

    expect(screen.queryByRole('button', { name: 'Good' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reveal answer' }))
    expect(screen.getByText('Keep source data on this device.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Good' }))
    expect(mutateAsync).toHaveBeenCalledWith({ cardId: 'study_card:one', rating: 'good' })
  })
})
