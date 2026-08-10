import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { KnowledgeRouteFrame, knowledgeRouteFolioMetadata } from './KnowledgeRouteFrames'

describe('knowledge route folio mapping', () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
  })

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
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '1'

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

  it('uses the legacy shell landmark when the folio flag is disabled', () => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'

    render(
      <main aria-label="Legacy application shell">
        <KnowledgeRouteFrame route="/capture">
          <p>Capture inbox</p>
        </KnowledgeRouteFrame>
      </main>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('region', { name: 'Capture' })).toHaveAttribute(
      'data-dn-folio-route-frame',
      'true',
    )
  })
})
