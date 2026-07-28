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
        'knowledge.resizeHorizontalSplit': 'Resize horizontal split',
        'knowledge.resizeVerticalSplit': 'Resize vertical split',
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

const research = {
  vaultId: 'vault:one',
  noteId: 'note:research',
  title: 'Research',
  relativePath: 'Projects/Research.md',
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

  it('associates each pane content panel with its currently active tab', () => {
    useKnowledgeWorkspaceStore.getState().openTab(research)
    renderLayout()
    const panel = screen.getByRole('tabpanel')
    const researchTab = screen.getByRole('tab', { name: 'Research' })

    expect(panel).toHaveAttribute('id', 'knowledge-panel-pane-1')
    expect(panel).toHaveAttribute('aria-labelledby', researchTab.id)

    fireEvent.click(screen.getByRole('tab', { name: 'Plan' }))

    expect(panel).toHaveAttribute(
      'aria-labelledby',
      screen.getByRole('tab', { name: 'Plan' }).id,
    )
  })

  it('derives one effective active tab for a hydrated pane whose active ID is null', () => {
    const current = useKnowledgeWorkspaceStore.getState()
    const paneWithNoActiveId = {
      ...current.panes['pane-1'],
      activeTabId: null,
    }
    current.replaceWorkspace({
      version: 1,
      activePaneId: 'pane-1',
      nextId: current.nextId,
      panes: { 'pane-1': paneWithNoActiveId },
      layout: { type: 'pane', paneId: 'pane-1' },
    })
    const renderPane = vi.fn((pane: { activeTabId: string | null }) => (
      <div>Rendered tab {pane.activeTabId ?? 'none'}</div>
    ))

    render(<KnowledgeWorkspaceLayout renderPane={renderPane} />)
    const firstTab = screen.getByRole('tab', { name: 'Plan' })
    const tabPanel = screen.getByRole('tabpanel')
    const effectiveTabId = paneWithNoActiveId.tabs[0].id

    expect(firstTab).toHaveAttribute('aria-selected', 'true')
    expect(firstTab).toHaveAttribute('tabindex', '0')
    expect(
      screen.getByRole('region', { name: /Knowledge pane pane-1: Plan/ }),
    ).toBeInTheDocument()
    expect(tabPanel).toHaveAttribute('aria-labelledby', firstTab.id)
    expect(renderPane).toHaveBeenCalledWith(
      expect.objectContaining({ activeTabId: effectiveTabId }),
    )
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId)
      .toBeNull()
  })

  it('preserves named, keyboard-focusable split directions and renders each pane once', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    const secondPaneId = store.splitPane('pane-1', 'horizontal')
    store.splitPane(secondPaneId, 'vertical')
    const renderPane = vi.fn((pane: { id: string }) => (
      <div>Content for {pane.id}</div>
    ))

    render(<KnowledgeWorkspaceLayout renderPane={renderPane} />)

    const horizontalSeparator = screen.getByRole('separator', {
      name: 'Resize horizontal split',
    })
    const verticalSeparator = screen.getByRole('separator', {
      name: 'Resize vertical split',
    })
    expect(horizontalSeparator).toHaveAttribute('tabindex', '0')
    expect(verticalSeparator).toHaveAttribute('tabindex', '0')
    expect(
      horizontalSeparator.closest('[data-panel-group-direction]'),
    ).toHaveAttribute('data-panel-group-direction', 'horizontal')
    expect(
      verticalSeparator.closest('[data-panel-group-direction]'),
    ).toHaveAttribute('data-panel-group-direction', 'vertical')
    expect(renderPane).toHaveBeenCalledTimes(3)
    expect(
      renderPane.mock.calls.map(([pane]) => pane.id).sort(),
    ).toEqual(['pane-1', 'pane-3', 'pane-5'])
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

  it('moves focus from a closed nested pane to the surviving active pane region', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Split pane right' }))
    const secondPane = screen.getByRole('region', {
      name: /Knowledge pane pane-3/,
    })
    fireEvent.click(
      within(secondPane).getByRole('button', { name: 'Split pane down' }),
    )
    const closeNestedPane = within(
      screen.getByRole('region', { name: /Knowledge pane pane-3/ }),
    ).getByRole('button', { name: 'Close pane' })
    closeNestedPane.focus()

    fireEvent.click(closeNestedPane)

    expect(
      screen.getByRole('region', { name: /Knowledge pane pane-1/ }),
    ).toHaveFocus()
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

  it('activates a pane when its toolbar container is clicked', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Split pane right' }))
    expect(useKnowledgeWorkspaceStore.getState().activePaneId).toBe('pane-3')

    fireEvent.click(
      screen.getByRole('toolbar', { name: /Knowledge pane pane-1/ }),
    )

    expect(useKnowledgeWorkspaceStore.getState().activePaneId).toBe('pane-1')
  })

  it('does not allow the last pane to close', () => {
    renderLayout()

    expect(screen.getByRole('button', { name: 'Close pane' })).toBeDisabled()
  })
})
