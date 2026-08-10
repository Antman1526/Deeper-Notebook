import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./KnowledgeLinksInspector', () => ({
  KnowledgeLinksInspector: () => <div data-testid="links-inspector">Connected notes</div>,
}))

import { KnowledgeIntelligenceRail } from './KnowledgeIntelligenceRail'

describe('KnowledgeIntelligenceRail', () => {
  it('renders contextual panels and unmounts its panel content when collapsed', () => {
    render(
      <KnowledgeIntelligenceRail
        activeContext={{ evidence: '4 source excerpts', properties: '2 properties', production: 'No production queued' }}
        onNavigate={vi.fn()}
      />,
    )

    const rail = screen.getByRole('complementary', { name: 'Research intelligence' })
    expect(screen.getByTestId('knowledge-evidence-lens')).toBeInTheDocument()
    expect(rail).toHaveTextContent('4 source excerpts')
    expect(screen.getByRole('button', { name: 'Connections' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Connections' }))
    expect(screen.getByTestId('links-inspector')).toBeInTheDocument()

    const collapse = screen.getByRole('button', { name: 'Collapse intelligence rail' })
    fireEvent.click(collapse)
    expect(collapse).toHaveFocus()
    expect(screen.queryByTestId('links-inspector')).not.toBeInTheDocument()
    expect(screen.queryByText('4 source excerpts')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand intelligence rail' })).toBeInTheDocument()
  })
})
