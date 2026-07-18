import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { EvidenceQualityBadge } from './EvidenceQualityBadge'

describe('EvidenceQualityBadge', () => {
  it('uses a distinct critical label for contradicted claims', () => {
    render(<EvidenceQualityBadge counts={{ contradicted: 1, partial: 4 }} />)
    expect(screen.getByLabelText('1 evidence issue')).toHaveTextContent('1 evidence issue')
  })

  it('reports supported evidence when no review state remains', () => {
    render(<EvidenceQualityBadge counts={{ supported: 3 }} />)
    expect(screen.getByLabelText('Evidence supported')).toBeInTheDocument()
  })

  it('is keyboard accessible when used to open a review surface', () => {
    const onClick = vi.fn()
    render(<EvidenceQualityBadge counts={{ unsupported: 1 }} onClick={onClick} />)
    fireEvent.keyDown(screen.getByLabelText('1 evidence issue'), { key: 'Enter' })
    expect(onClick).toHaveBeenCalledOnce()
  })
})
