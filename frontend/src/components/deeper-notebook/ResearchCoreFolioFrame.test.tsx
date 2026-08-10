import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ResearchCoreFolioFrame } from './ResearchCoreFolioFrame'

describe('ResearchCoreFolioFrame', () => {
  it('frames the existing knowledge regions without introducing another main landmark', () => {
    render(
      <ResearchCoreFolioFrame
        header={<header>Research Core</header>}
        index={<aside aria-label="Knowledge index">Index</aside>}
        workspace={<main aria-label="Knowledge workspace">Workspace</main>}
        lens={<aside aria-label="Evidence lens">Lens</aside>}
        overlays={<div>Overlay</div>}
      />,
    )

    expect(screen.getByTestId('research-core-folio')).toBeInTheDocument()
    expect(screen.getByTestId('research-core-folio-header')).toHaveTextContent('Research Core')
    expect(screen.getByTestId('research-core-folio-index')).toHaveTextContent('Index')
    expect(screen.getByTestId('research-core-folio-workspace')).toHaveTextContent('Workspace')
    expect(screen.getByTestId('research-core-folio-lens')).toHaveTextContent('Lens')
    expect(screen.getByTestId('research-core-folio-overlays')).toHaveTextContent('Overlay')
    expect(screen.getAllByRole('main')).toHaveLength(1)
  })
})
