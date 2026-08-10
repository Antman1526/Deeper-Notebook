import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EvidenceStudioFolio } from './EvidenceStudioFolio'

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
