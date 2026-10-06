import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EpisodeResearchReceipt } from './EpisodeResearchReceipt'

// Echo interpolation values so assertions still cover the numbers rendered.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key} ${JSON.stringify(options)}` : key),
  }),
}))

describe('EpisodeResearchReceipt', () => {
  it('labels the receipt provenance plainly, without an internal phase label', () => {
    render(<EpisodeResearchReceipt selectionSummary={{ version: 1, total_count: 1, included_count: 1 }} />)

    expect(screen.getByText('podcasts.episodeResearchReceipt.provenance')).toBeVisible()
    expect(document.body).not.toHaveTextContent(/Phase[- ]\d/)
  })

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

    expect(screen.getByRole('heading', { name: 'podcasts.episodeResearchReceipt.title' })).toBeVisible()
    expect(screen.getByText('podcasts.episodeResearchReceipt.sourcesIncluded {"included":2,"total":2}')).toBeVisible()
    expect(screen.getByText('podcasts.episodeResearchReceipt.externalReadOnly {"external":2}')).toBeVisible()
    expect(screen.getByText('podcasts.episodeResearchReceipt.routesRecordedOne {"count":1}')).toBeVisible()
    expect(screen.getByText('Research team')).toBeVisible()
    expect(screen.queryByText('Research/Private.md')).not.toBeInTheDocument()
    expect(screen.queryByText('local-podcast')).not.toBeInTheDocument()
  })
})
