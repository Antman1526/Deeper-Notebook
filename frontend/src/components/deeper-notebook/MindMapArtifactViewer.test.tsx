import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MindMapArtifactViewer } from './MindMapArtifactViewer'
import { parseMindMap } from './StudyArtifactViewers'

vi.mock('@xyflow/react', () => ({
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  ReactFlow: ({ nodes, onNodeClick }: { nodes: Array<{ id: string; data: { label: string } }>; onNodeClick: (event: React.MouseEvent, node: { id: string }) => void }) => (
    <div data-testid="react-flow">{nodes.map((node) => <button key={node.id} onClick={(event) => onNodeClick(event, node)}>{node.data.label}</button>)}</div>
  ),
}))

const nodes = parseMindMap(`- Root (contains) [S1]
  - Child (supports) [S2]
    - Detail [S2]`)

describe('MindMapArtifactViewer', () => {
  it('derives stable child-index paths from a typed outline', () => {
    expect(nodes[0]).toMatchObject({ id: '0', label: 'Root', relationship: 'contains', citations: ['[S1]'] })
    expect(nodes[0].children[0]).toMatchObject({ id: '0/0', label: 'Child', relationship: 'supports', citations: ['[S2]'] })
    expect(nodes[0].children[0].children[0].id).toBe('0/0/0')
  })

  it('supports node details, keyboard traversal, and branch collapse', () => {
    render(<MindMapArtifactViewer nodes={nodes} />)
    const canvas = screen.getByLabelText(/Mind map canvas/i)
    expect(screen.getAllByText('Root').length).toBeGreaterThan(0)

    fireEvent.keyDown(canvas, { key: 'ArrowDown' })
    expect(screen.getAllByText('Child').length).toBeGreaterThan(0)
    fireEvent.keyDown(canvas, { key: 'Enter' })
    expect(screen.queryByText('Detail')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /expand branch/i })).toBeInTheDocument()
  })
})
