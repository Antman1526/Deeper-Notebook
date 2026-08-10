import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EvidenceStudioFolio } from './EvidenceStudioFolio'
import { PodcastStudioFolio } from './PodcastStudioFolio'

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

    expect(screen.getByRole('region', { name: 'Evidence Studio folio' })).toBeInTheDocument()
    expect(screen.getByLabelText('Source desk')).toHaveTextContent('Upload sources')
    expect(screen.getByLabelText('Editorial brief')).toHaveTextContent('Notebook mode')
    expect(screen.getByLabelText('Artifact pages')).toHaveTextContent('Generate notebook')
    expect(screen.getByLabelText('Trust margin')).toHaveTextContent('3 citations retained')
    expect(screen.getByText('Ready for explicit generation')).toBeInTheDocument()
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

    expect(screen.getByRole('region', { name: 'Podcast production folio' })).toBeInTheDocument()
    expect(screen.getByLabelText('Research set')).toHaveTextContent('2 selected sources')
    expect(screen.getByLabelText('Editorial brief')).toHaveTextContent('Edit brief')
    expect(screen.getByLabelText('Outline storyboard')).toHaveTextContent('Edit outline')
    expect(screen.getByLabelText('Model plan')).toHaveTextContent('Local route')
    expect(screen.getByLabelText('Production gate')).toHaveTextContent('Prepare production review')
    expect(screen.getByLabelText('Production review')).toHaveTextContent('Confirm only after review')
  })
})
