import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { KnowledgeRouteFrame, knowledgeRouteFolioMetadata } from './KnowledgeRouteFrames'

describe('knowledge route folio mapping', () => {
  it.each([
    ['/sources', 'Sources'],
    ['/capture', 'Capture'],
    ['/notebooks', 'Notebooks'],
    ['/search', 'Ask & Search'],
    ['/study', 'Study'],
  ] as const)('maps %s to the %s folio', (route, title) => {
    expect(knowledgeRouteFolioMetadata[route]).toMatchObject({ title })
  })

  it('composes the shared folio landmark with the route metadata and actions', () => {
    render(
      <KnowledgeRouteFrame route="/capture" actions={<button type="button">Add source</button>}>
        <p>Capture inbox</p>
      </KnowledgeRouteFrame>,
    )

    expect(screen.getByRole('main', { name: 'Capture' })).toHaveAttribute(
      'data-dn-folio-route-frame',
      'true',
    )
    expect(screen.getByText('Collect')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add source' })).toBeInTheDocument()
    expect(screen.getByText('Capture inbox')).toBeInTheDocument()
  })
})
