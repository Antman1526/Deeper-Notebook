import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  InfographicViewer,
  type InfographicVisualDocument,
  isInfographicDocument,
  isSlideDeckDocument,
  SlideDeckViewer,
  type SlideDeckVisualDocument,
} from './VisualArtifactViewers'

const slideDeck: SlideDeckVisualDocument = {
  schema_version: 1,
  artifact_type: 'slide_deck',
  title: 'Evidence Slides',
  audience: 'Researchers',
  slides: [
    {
      title: 'Grounded output',
      bullets: ['Claims remain traceable.', 'Exports stay local.'],
      speaker_notes: 'Explain the evidence trail.',
      visual_direction: 'Use a simple source flow.',
      citations: ['[S1]'],
    },
    {
      title: 'Private workflow',
      bullets: ['No hosted renderer is required.'],
      speaker_notes: '',
      visual_direction: '',
      citations: ['[S2]'],
    },
  ],
}

const infographic: InfographicVisualDocument = {
  schema_version: 1,
  artifact_type: 'infographic',
  title: 'Evidence at a glance',
  orientation: 'landscape',
  panels: [
    {
      kind: 'metric',
      heading: 'Coverage',
      value: '95%',
      body: 'Resolved citations',
      citations: ['[S1]'],
    },
    {
      kind: 'process',
      heading: 'Workflow',
      value: '',
      body: 'Collect, validate, render, review.',
      citations: ['[S2]'],
    },
  ],
}

describe('visual artifact document guards', () => {
  it('accepts valid v1 visual documents and rejects malformed values', () => {
    expect(isSlideDeckDocument(slideDeck)).toBe(true)
    expect(isSlideDeckDocument({ ...slideDeck, slides: 'invalid' })).toBe(false)
    expect(isInfographicDocument(infographic)).toBe(true)
    expect(isInfographicDocument({ ...infographic, orientation: 'poster' })).toBe(false)
  })
})

describe('SlideDeckViewer', () => {
  it('navigates a fixed slide stage with buttons and arrow keys', () => {
    render(<SlideDeckViewer document={slideDeck} />)

    const workspace = screen.getByRole('region', { name: 'Slide deck' })
    expect(screen.getByRole('heading', { name: 'Evidence Slides' })).toBeInTheDocument()
    expect(screen.getByText('Prepared for Researchers')).toBeInTheDocument()
    expect(screen.getByText(/Slide 1 of 3/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Grounded output' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Private workflow' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next slide' }))
    expect(screen.getByRole('heading', { name: 'Grounded output' })).toBeInTheDocument()
    expect(screen.getByText(/Slide 2 of 3/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next slide' }))
    expect(screen.getByRole('heading', { name: 'Private workflow' })).toBeInTheDocument()
    expect(screen.getByText(/Slide 3 of 3/)).toBeInTheDocument()

    fireEvent.keyDown(workspace, { key: 'ArrowLeft' })
    expect(screen.getByRole('heading', { name: 'Grounded output' })).toBeInTheDocument()
  })

  it('reveals speaker notes, visual direction, and citations', () => {
    render(<SlideDeckViewer document={slideDeck} />)

    fireEvent.click(screen.getByRole('button', { name: 'Next slide' }))
    expect(screen.getByText('[S1]')).toBeInTheDocument()
    expect(screen.queryByText('Explain the evidence trail.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show speaker notes' }))
    expect(screen.getByText('Explain the evidence trail.')).toBeInTheDocument()
    expect(screen.getAllByText('Use a simple source flow.')).toHaveLength(2)
  })
})

describe('InfographicViewer', () => {
  it('renders orientation, panel kinds, values, and citations', () => {
    render(<InfographicViewer document={infographic} />)

    const visual = screen.getByRole('figure', { name: 'Evidence at a glance' })
    expect(visual).toHaveAttribute('data-orientation', 'landscape')
    expect(screen.getByText('metric')).toBeInTheDocument()
    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText('process')).toBeInTheDocument()
    expect(screen.getByText('[S1]')).toBeInTheDocument()
    expect(screen.getByText('[S2]')).toBeInTheDocument()
  })
})
