import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceApprovalPanel } from './SourceApprovalPanel'

describe('SourceApprovalPanel', () => {
  it('requires an explicit accepted candidate set before import', () => {
    const onApprove = vi.fn()
    render(<SourceApprovalPanel onApprove={onApprove} candidates={[
      { candidate_id: 'one', url: 'https://example.com/a', title: 'A', domain: 'example.com', snippet: 'First', search_query: 'topic', decision: 'pending' },
      { candidate_id: 'two', url: 'https://example.org/b', title: 'B', domain: 'example.org', snippet: 'Second', search_query: 'topic', decision: 'pending' },
    ]} />)

    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getByRole('button', { name: 'Approve selected sources' }))

    expect(onApprove).toHaveBeenCalledWith(['one'])
  })

  it('shows evidence receipts while keeping legacy candidates selectable', () => {
    const sourceFingerprint = 'a'.repeat(64)
    const evidenceId = 'b'.repeat(64)

    render(<SourceApprovalPanel onApprove={vi.fn()} candidates={[
      {
        candidate_id: 'evidence',
        url: 'https://example.com/evidence',
        title: 'Evidence result',
        domain: 'example.com',
        snippet: 'Evidence snippet',
        search_query: 'topic',
        decision: 'pending',
        evidence: {
          query: 'topic',
          provider: 'tavily',
          title: 'Evidence result',
          url: 'https://example.com/evidence',
          snippet: 'Evidence snippet',
          retrieved_at: '2026-08-08T12:34:56Z',
          freshness: 'stale',
          degraded: true,
          source_fingerprint: sourceFingerprint,
          evidence_id: evidenceId,
        },
      },
      {
        candidate_id: 'legacy',
        url: 'https://example.org/legacy',
        title: 'Legacy result',
        domain: 'example.org',
        snippet: 'Legacy snippet',
        search_query: 'topic',
        decision: 'pending',
      },
    ]} />)

    expect(screen.getByText('tavily')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('Fallback provider')).toBeInTheDocument()
    expect(screen.getByText('aaaaaaaa…aaaaaaaa')).toBeInTheDocument()
    expect(screen.getByText('bbbbbbbb…bbbbbbbb')).toBeInTheDocument()
    expect(screen.getByLabelText(new RegExp(sourceFingerprint))).toBeInTheDocument()
    expect(screen.getByText('Legacy result')).toBeInTheDocument()

    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(2)
    fireEvent.click(checkboxes[1])
    expect(checkboxes[1]).not.toBeChecked()
  })
})
