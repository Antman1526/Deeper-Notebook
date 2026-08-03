import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

const flowProps = vi.hoisted(() => ({
  viewport: undefined as undefined | { x: number; y: number; zoom: number },
}))

vi.mock('@xyflow/react/dist/style.css', () => ({}))
vi.mock('./vault.css', () => ({}))

vi.mock('@xyflow/react', () => ({
  Background: () => null,
  Controls: () => null,
  ReactFlow: ({
    children,
    viewport,
    fitView,
    onMoveEnd,
  }: {
    children: React.ReactNode
    viewport?: { x: number; y: number; zoom: number }
    fitView: boolean
    onMoveEnd: (
      event: null,
      viewport: { x: number; y: number; zoom: number },
    ) => void
  }) => {
    flowProps.viewport = viewport
    return (
      <div data-fit-view={fitView}>
        <button
          type="button"
          onClick={() => onMoveEnd(null, { x: 7, y: -2, zoom: 1.5 })}
        >
          Move graph
        </button>
        {children}
      </div>
    )
  },
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { VaultGraph } from './VaultGraph'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

describe('VaultGraph controlled viewport', () => {
  it('passes a controlled viewport to React Flow and reports onMoveEnd', () => {
    const onMoveEnd = vi.fn()
    const onBookmarkContext = vi.fn()
    render(
      <VaultGraph
        graph={{
          nodes: [{
            id: 'note:one', title: 'One', source_format: 'markdown',
          }],
          edges: [],
        }}
        unresolved={[]}
        onNavigate={vi.fn()}
        viewport={{ x: 3, y: 6, zoom: 2 }}
        onMoveEnd={onMoveEnd}
        rootDocumentId="knowledge_engine_document:one"
        spaceIds={['knowledge_engine_space:research']}
        onBookmarkContext={onBookmarkContext}
      />,
    )

    expect(flowProps.viewport).toEqual({ x: 3, y: 6, zoom: 2 })
    expect(screen.getByText('Move graph').parentElement).toHaveAttribute('data-fit-view', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Move graph' }))
    expect(onMoveEnd).toHaveBeenCalledWith({ x: 7, y: -2, zoom: 1.5 })
    expect(onBookmarkContext).toHaveBeenCalledWith({
      rootDocumentId: 'knowledge_engine_document:one',
      spaceIds: ['knowledge_engine_space:research'],
      relationKinds: [],
      viewport: { x: 3, y: 6, zoom: 2 },
    })
  })

  it('does not repeat bookmark publication after an implicit empty relation filter rerenders its parent', async () => {
    const onBookmarkContext = vi.fn()
    function BookmarkContextHarness() {
      const [, setBookmarkContext] = useState<unknown>(null)
      return <VaultGraph
        graph={{
          nodes: [{ id: 'note:one', title: 'One', source_format: 'markdown' }],
          edges: [],
        }}
        unresolved={[]}
        onNavigate={vi.fn()}
        viewport={{ x: 3, y: 6, zoom: 2 }}
        rootDocumentId="knowledge_engine_document:one"
        spaceIds={['knowledge_engine_space:research']}
        onBookmarkContext={(context) => {
          onBookmarkContext(context)
          setBookmarkContext(context)
        }}
      />
    }

    render(<BookmarkContextHarness />)

    await waitFor(() => expect(onBookmarkContext).toHaveBeenCalledTimes(1))
  })

  it('opens a bounded unified graph selection through review-only podcast state', () => {
    usePodcastStudioStore.getState().dismiss()
    render(
      <VaultGraph
        graph={{
          nodes: [{
            id: 'note:one', title: 'One', source_format: 'markdown',
            knowledge_document_id: 'knowledge_engine_document:one',
          }],
          edges: [],
        }}
        unresolved={[]}
        onNavigate={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Turn graph into podcast' }))

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [{
        kind: 'graph_selection', documentIds: ['knowledge_engine_document:one'],
      }],
    })
  })
})
