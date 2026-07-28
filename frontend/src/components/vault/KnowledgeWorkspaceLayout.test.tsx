import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { KnowledgeWorkspaceLayout } from './KnowledgeWorkspaceLayout'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { title?: string }) => {
      const labels: Record<string, string> = {
        'knowledge.openTabs': 'Open tabs',
        'knowledge.knowledgeWorkspace': 'Knowledge workspace',
        'knowledge.knowledgePane': 'Knowledge pane',
        'knowledge.splitPaneRight': 'Split pane right',
        'knowledge.splitPaneDown': 'Split pane down',
        'knowledge.closePane': 'Close pane',
      }
      if (key === 'knowledge.closeTab') return `Close ${options?.title ?? ''}`.trim()
      return labels[key] ?? key
    },
  }),
}))

const plan = {
  vaultId: 'vault:one',
  noteId: 'note:plan',
  title: 'Plan',
  relativePath: 'Projects/Plan.md',
} as const

function renderLayout() {
  return render(
    <KnowledgeWorkspaceLayout
      renderPane={(pane) => <div>Content for {pane.id}</div>}
    />,
  )
}

describe('KnowledgeWorkspaceLayout', () => {
  beforeEach(() => {
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
    useKnowledgeWorkspaceStore.getState().openTab(plan)
  })

  it('renders recursive right and down splits as accessible pane regions', () => {
    renderLayout()
    const firstPane = screen.getByRole('region', {
      name: /Knowledge pane pane-1/,
    })

    fireEvent.click(
      within(firstPane).getByRole('button', { name: 'Split pane right' }),
    )

    const panesAfterRightSplit = screen.getAllByRole('region', {
      name: /Knowledge pane pane-/,
    })
    fireEvent.click(
      within(panesAfterRightSplit[1]).getByRole('button', {
        name: 'Split pane down',
      }),
    )

    expect(
      screen.getAllByRole('region', { name: /Knowledge pane pane-/ }),
    ).toHaveLength(3)
    expect(screen.getByText('Content for pane-1')).toBeInTheDocument()
    expect(screen.getByText('Content for pane-3')).toBeInTheDocument()
    expect(screen.getByText('Content for pane-5')).toBeInTheDocument()
  })

  it('collapses a nested split when its second pane is closed', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Split pane right' }))
    const secondPane = screen.getByRole('region', {
      name: /Knowledge pane pane-3/,
    })
    fireEvent.click(
      within(secondPane).getByRole('button', { name: 'Split pane down' }),
    )

    fireEvent.click(
      within(
        screen.getByRole('region', { name: /Knowledge pane pane-3/ }),
      ).getByRole('button', { name: 'Close pane' }),
    )

    expect(
      screen.getAllByRole('region', { name: /Knowledge pane pane-/ }),
    ).toHaveLength(2)
    expect(
      screen.queryByRole('region', { name: /Knowledge pane pane-3/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Content for pane-5')).toBeInTheDocument()
  })

  it('activates a pane when its region receives focus', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Split pane right' }))
    const firstPane = screen.getByRole('region', {
      name: /Knowledge pane pane-1/,
    })

    fireEvent.focus(firstPane)

    expect(useKnowledgeWorkspaceStore.getState().activePaneId).toBe('pane-1')
    expect(firstPane).toHaveAttribute('data-active', 'true')
  })

  it('does not allow the last pane to close', () => {
    renderLayout()

    expect(screen.getByRole('button', { name: 'Close pane' })).toBeDisabled()
  })
})
