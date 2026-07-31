import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceRestorePlan } from '@/lib/api/knowledge-navigation'
import { WorkspaceRestoreDialog } from './WorkspaceRestoreDialog'

const stalePlan = (): WorkspaceRestorePlan => ({
  workspaceId: 'named_knowledge_workspace:research', revision: 3,
  activePaneId: 'pane-1', nextId: 3,
  panes: {
    'pane-1': {
      id: 'pane-1', activeTabId: 'tab-1', tabs: [{
        id: 'tab-1', displayLabel: 'Research note', viewMode: 'reading',
        target: { kind: 'document', documentId: 'knowledge_engine_document:research' },
        targetState: 'stale', targetDocument: null,
      }],
    },
  },
  layout: { type: 'pane', paneId: 'pane-1' },
  navigation: {
    utilityMode: 'workspaces', sidebarVisible: true, sidebarWidth: 320,
    activeBookmarkFolderId: null, bookmarkTags: [], sourceTreeQuery: '',
    searchQuery: '', searchMode: 'text', activeDraftId: null, selectedSpaceIds: [],
    authorityFilters: [], metricsVisible: true,
  },
  summary: { available: 0, stale: 1, unavailable: 0, missing: 0 },
})

describe('WorkspaceRestoreDialog', () => {
  it('does not apply a stale restore plan before confirmation', () => {
    const onOpenAvailable = vi.fn()
    render(<WorkspaceRestoreDialog plan={stalePlan()} onOpenAvailable={onOpenAvailable} onCancel={vi.fn()} />)

    expect(screen.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible()
    expect(onOpenAvailable).not.toHaveBeenCalled()
  })

  it('offers Open available and Cancel with target-state summary rows', () => {
    const onOpenAvailable = vi.fn()
    const onCancel = vi.fn()
    render(<WorkspaceRestoreDialog plan={stalePlan()} onOpenAvailable={onOpenAvailable} onCancel={onCancel} />)

    expect(screen.getByText('Research note')).toBeVisible()
    expect(screen.getByText('stale')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Open available' }))
    expect(onOpenAvailable).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
