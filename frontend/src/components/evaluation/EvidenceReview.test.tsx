import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EvidenceReview } from './EvidenceReview'

const useLatestEvaluation = vi.fn()

vi.mock('@/lib/hooks/use-evaluation', () => ({
  useLatestEvaluation: (...args: unknown[]) => useLatestEvaluation(...args),
}))

describe('EvidenceReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows an honest empty state for a missing 404 evaluation', () => {
    useLatestEvaluation.mockReturnValue({ data: null, isLoading: false, isError: false })

    render(<EvidenceReview notebookId="notebook:one" messageId="message:one" />)

    expect(screen.getByText('No evidence review yet')).toBeInTheDocument()
  })

  it('shows loading, failed, and completed states without inventing support', () => {
    useLatestEvaluation.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    const { rerender } = render(
      <EvidenceReview notebookId="notebook:one" messageId="message:one" />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(/checking evidence/i)

    useLatestEvaluation.mockReturnValue({ data: undefined, isLoading: false, isError: true })
    rerender(<EvidenceReview notebookId="notebook:one" messageId="message:one" />)
    expect(screen.getByText('Evidence review unavailable')).toBeInTheDocument()

    useLatestEvaluation.mockReturnValue({
      data: {
        run: {
          id: 'evaluation_run:one',
          notebook_id: 'notebook:one',
          message_id: 'message:one',
          evaluator_version: 'deterministic-v1',
          metrics: {},
        },
        status: 'failed',
        counts: { supported: 0, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
        verdicts: [],
      },
      isLoading: false,
      isError: false,
    })
    rerender(<EvidenceReview notebookId="notebook:one" messageId="message:one" />)
    expect(screen.getByText('Evidence review failed')).toBeInTheDocument()
  })

  it('opens and closes the claim drawer from the keyboard-accessible badge', () => {
    useLatestEvaluation.mockReturnValue({
      data: {
        run: {
          id: 'evaluation_run:one',
          notebook_id: 'notebook:one',
          message_id: 'message:one',
          evaluator_version: 'deterministic-v1',
          metrics: {},
        },
        status: 'completed',
        counts: { supported: 1, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
        verdicts: [{
          claim: 'A grounded claim',
          status: 'supported',
          confidence: 1,
          citation_markers: ['[S1]'],
          evidence: [],
          explanation: 'Supported.',
        }],
      },
      isLoading: false,
      isError: false,
    })

    render(<EvidenceReview notebookId="notebook:one" messageId="message:one" />)
    const badge = screen.getByRole('button', { name: /evidence supported/i })
    badge.focus()
    fireEvent.keyDown(badge, { key: 'Enter' })
    expect(screen.getByRole('dialog', { name: 'Evidence review' })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Evidence review' })).not.toBeInTheDocument()
  })
})
