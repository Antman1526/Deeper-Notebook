import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CitationCoverageBadge } from './CitationCoverageBadge'

describe('CitationCoverageBadge', () => {
  it('shows when an artifact has no stored citations', () => {
    render(<CitationCoverageBadge citationCount={0} />)

    expect(screen.getByText('No citations')).toBeInTheDocument()
  })

  it('shows singular citation coverage', () => {
    render(<CitationCoverageBadge citationCount={1} />)

    expect(screen.getByText('1 citation')).toBeInTheDocument()
  })

  it('shows plural citation coverage', () => {
    render(<CitationCoverageBadge citationCount={4} />)

    expect(screen.getByText('4 citations')).toBeInTheDocument()
  })
})
