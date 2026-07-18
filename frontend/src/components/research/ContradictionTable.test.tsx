import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ContradictionTable } from './ContradictionTable'

describe('ContradictionTable', () => {
  it('states when no validated comparison has been published', () => {
    render(<ContradictionTable comparison={{ agreements: [], contradictions: [], gaps: [] }} />)
    expect(screen.getByText(/Comparison results will appear/)).toBeInTheDocument()
  })
})
