import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  selectActiveKnowledgeTab,
  selectPaneCount,
  useKnowledgeWorkspaceStore,
} from './knowledge-workspace-store'

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

const decisions = {
  vaultId: 'vault:one',
  noteId: 'note:decisions',
  title: 'Decisions',
  relativePath: 'Projects/Decisions.md',
} as const

describe('knowledge workspace store', () => {
  beforeEach(() => {
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('starts as an immediate one-pane workspace without browser persistence', () => {
    const persistSpy = vi.spyOn(Storage.prototype, 'setItem')

    useKnowledgeWorkspaceStore.getState().openTab(plan)

    expect(useKnowledgeWorkspaceStore.getState()).toMatchObject({
      version: 1,
      activePaneId: 'pane-1',
      nextId: 3,
      hydrated: false,
      layout: { type: 'pane', paneId: 'pane-1' },
    })
    expect(persistSpy).not.toHaveBeenCalled()
    persistSpy.mockRestore()
  })

  it('deduplicates an open note inside the active pane', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    store.openTab(plan)

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(1)
    expect(selectActiveKnowledgeTab(useKnowledgeWorkspaceStore.getState())).toMatchObject(plan)
  })

  it('creates recursively nestable horizontal and vertical splits', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const second = store.splitPane('pane-1', 'horizontal')
    store.splitPane(second, 'vertical')

    expect(selectPaneCount(useKnowledgeWorkspaceStore.getState())).toBe(3)
    expect(useKnowledgeWorkspaceStore.getState().panes[second].tabs[0]).toMatchObject(plan)
  })

  it('closes a split pane without losing its sibling', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const second = store.splitPane('pane-1', 'horizontal')
    store.closePane(second)

    expect(useKnowledgeWorkspaceStore.getState().layout)
      .toEqual({ type: 'pane', paneId: 'pane-1' })
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject(plan)
    expect(useKnowledgeWorkspaceStore.getState().activePaneId).toBe('pane-1')
  })

  it('selects the next neighbor and then the previous neighbor when closing tabs', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    store.openTab(research)
    store.openTab(decisions)
    const pane = useKnowledgeWorkspaceStore.getState().panes['pane-1']

    store.activateTab('pane-1', pane.tabs[1].id)
    store.closeTab('pane-1', pane.tabs[1].id)
    expect(selectActiveKnowledgeTab(useKnowledgeWorkspaceStore.getState())?.noteId)
      .toBe('note:decisions')

    const current = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    store.closeTab('pane-1', current.tabs[1].id)
    expect(selectActiveKnowledgeTab(useKnowledgeWorkspaceStore.getState())?.noteId)
      .toBe('note:plan')
  })

  it('stores view mode independently per tab', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    store.openTab(research)
    const pane = useKnowledgeWorkspaceStore.getState().panes['pane-1']

    store.setTabViewMode('pane-1', pane.tabs[0].id, 'graph')

    const tabs = useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs
    expect(tabs[0].viewMode).toBe('graph')
    expect(tabs[1].viewMode).toBe('reading')
  })
})
