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
})
