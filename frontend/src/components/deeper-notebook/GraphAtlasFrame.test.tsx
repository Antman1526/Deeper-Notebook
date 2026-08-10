import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { GraphAtlasFrame } from './GraphAtlasFrame'

describe('GraphAtlasFrame', () => {
  it('frames existing graph controls, canvas, legend, and inspector without adding graph behavior', () => {
    render(
      <GraphAtlasFrame
        actions={<button type="button">Turn graph into podcast</button>}
        legend={<ul><li>Markdown source</li></ul>}
        canvas={<div>Graph canvas</div>}
        inspector={<p>Open a connected note to inspect it.</p>}
      />,
    )

    expect(screen.getByRole('region', { name: 'Connection atlas' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Connection atlas' })).toBeInTheDocument()
    expect(screen.getByLabelText('Graph legend')).toHaveTextContent('Markdown source')
    expect(screen.getByLabelText('Graph inspector')).toHaveTextContent('Open a connected note')
    expect(screen.getByRole('button', { name: 'Turn graph into podcast' })).toBeInTheDocument()
  })
})
