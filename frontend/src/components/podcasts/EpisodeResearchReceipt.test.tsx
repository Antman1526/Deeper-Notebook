import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EpisodeResearchReceipt } from './EpisodeResearchReceipt'

describe('EpisodeResearchReceipt', () => {
  it('shows aggregate selection and routing receipts without source details', () => {
    render(
      <EpisodeResearchReceipt
        selectionSummary={{
          version: 1,
          total_count: 2,
          included_count: 2,
          authority_counts: { external_read_only: 2 },
        }}
        selectionFingerprint={'a'.repeat(64)}
        editorialBrief={{
          central_question: 'What changes after the research is connected?',
          audience: 'Research team',
          outline: ['Context', 'Decision'],
        }}
        modelPlanReceipts={[{ version: 1, role: 'podcast_outline', outcome: 'ready', reason: 'Verified local route.' }]}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Research receipt' })).toBeVisible()
    expect(screen.getByText('2 of 2 sources included')).toBeVisible()
    expect(screen.getByText('2 external read-only')).toBeVisible()
    expect(screen.getByText('1 local route recorded')).toBeVisible()
    expect(screen.getByText('Research team')).toBeVisible()
    expect(screen.queryByText('Research/Private.md')).not.toBeInTheDocument()
    expect(screen.queryByText('local-podcast')).not.toBeInTheDocument()
  })
})
