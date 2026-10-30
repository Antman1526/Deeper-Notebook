import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { EvidenceStudioFolio } from './EvidenceStudioFolio'
import { PodcastStudioFolio } from './PodcastStudioFolio'

afterEach(() => {
  delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
})

describe('EvidenceStudioFolio', () => {
  it('lays out existing source, brief, artifact, trust, and status slots without owning actions', () => {
    render(
      <EvidenceStudioFolio
        sourceDesk={<button type="button">Upload sources</button>}
        editorialBrief={<button type="button">Notebook mode</button>}
        artifactPages={<><button type="button">Generate notebook</button><a href="/export">Export artifact</a></>}
        trustMargin={<p>3 citations retained</p>}
        status={<p>Ready for explicit generation</p>}
      />,
    )

    expect(screen.getByRole('main', { name: 'workspace.evidenceStudioFolio.ariaLabel' })).toBeInTheDocument()
    expect(screen.getByLabelText('workspace.evidenceStudioFolio.sourceDesk')).toHaveTextContent('Upload sources')
    expect(screen.getByLabelText('workspace.evidenceStudioFolio.editorialBrief')).toHaveTextContent('Notebook mode')
    expect(screen.getByLabelText('workspace.evidenceStudioFolio.artifactPages')).toHaveTextContent('Generate notebook')
    expect(screen.getByLabelText('workspace.evidenceStudioFolio.trustMargin')).toHaveTextContent('3 citations retained')
    expect(screen.getByText('Ready for explicit generation')).toBeInTheDocument()
  })

  it('retains one studio-owned main landmark in the rollback shell', () => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'

    render(
      <div data-testid="legacy-application-shell">
        <EvidenceStudioFolio
          sourceDesk={<p>Upload sources</p>}
          editorialBrief={<p>Notebook mode</p>}
          artifactPages={<p>Generate notebook</p>}
        />
      </div>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'workspace.evidenceStudioFolio.ariaLabel' })).toBeInTheDocument()
  })
})

describe('PodcastStudioFolio', () => {
  it('frames existing production stages without owning their review or confirmation actions', () => {
    render(
      <PodcastStudioFolio
        researchSet={<p>2 selected sources</p>}
        editorialBrief={<button type="button">Edit brief</button>}
        storyboard={<button type="button">Edit outline</button>}
        modelPlan={<p>Local route</p>}
        production={<button type="button">Prepare production review</button>}
        review={<p>Confirm only after review</p>}
      />,
    )

    expect(screen.getByRole('region', { name: 'podcasts.podcastStudioFolio.productionFolio' })).toBeInTheDocument()
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.researchSet')).toHaveTextContent('2 selected sources')
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.editorialBrief')).toHaveTextContent('Edit brief')
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.outlineStoryboard')).toHaveTextContent('Edit outline')
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.modelPlan')).toHaveTextContent('Local route')
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.productionGate')).toHaveTextContent('Prepare production review')
    expect(screen.getByLabelText('podcasts.podcastStudioFolio.productionReview')).toHaveTextContent('Confirm only after review')
  })
})
