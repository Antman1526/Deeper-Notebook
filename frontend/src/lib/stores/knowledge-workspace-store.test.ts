import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  defaultKnowledgeWorkspace,
  serializeKnowledgeWorkspace,
  type KnowledgeLayoutNode,
  type OpenKnowledgeTab,
} from '@/lib/api/knowledge-workspace'
import {
  selectActiveKnowledgeTab,
  selectPaneCount,
  useKnowledgeWorkspaceStore,
} from './knowledge-workspace-store'
import { useOverlayDraftStore } from './overlay-draft-store'

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

  it('applies a named workspace in one revision and preserves drafts', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab({ ...plan, sourceAuthority: 'overlay' })
    const tabId = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId!
    useOverlayDraftStore.setState({ drafts: { [`pane-1:${tabId}`]: {} as never } })
    const before = useKnowledgeWorkspaceStore.getState().revision

    expect(store.applyNamedWorkspace(defaultKnowledgeWorkspace())).toBe(true)
    expect(useKnowledgeWorkspaceStore.getState().revision).toBe(before + 1)
    expect(useOverlayDraftStore.getState().drafts).toHaveProperty(`pane-1:${tabId}`)
  })

  it('leaves current state unchanged when named workspace validation fails', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    const before = useKnowledgeWorkspaceStore.getState()
    const invalid = defaultKnowledgeWorkspace()
    invalid.panes['pane-1'].tabs = [{
      id: 'tab-1', vaultId: 'vault:one', noteId: 'note:one', title: 'One',
      relativePath: '/unsafe.md', viewMode: 'reading', sourceAuthority: 'external-vault',
      knowledgeDocumentId: null, graphViewport: { x: 0, y: 0, zoom: 1 },
    }]
    invalid.panes['pane-1'].activeTabId = 'tab-1'

    expect(store.applyNamedWorkspace(invalid)).toBe(false)
    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
  })

  it('deduplicates an open note inside the active pane', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    store.openTab(plan)

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(1)
    expect(selectActiveKnowledgeTab(useKnowledgeWorkspaceStore.getState())).toMatchObject(plan)
  })

  it('keeps overlay and external tabs distinct for identical note IDs', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    store.openTab({ ...plan, sourceAuthority: 'overlay' })

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
      .toHaveLength(2)
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

  it('clears ephemeral overlay drafts when their tab closes or the workspace resets', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab({ ...plan, sourceAuthority: 'overlay' })
    const tabId = useKnowledgeWorkspaceStore
      .getState().panes['pane-1'].activeTabId!
    const viewId = `pane-1:${tabId}`
    useOverlayDraftStore.setState({
      drafts: { [viewId]: {} as never },
    })

    store.closeTab('pane-1', tabId)
    expect(useOverlayDraftStore.getState().drafts).toEqual({})

    useOverlayDraftStore.setState({
      drafts: { 'pane-1:stale': {} as never },
    })
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
    expect(useOverlayDraftStore.getState().drafts).toEqual({})
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

  it('reconciles a hydrated tab to canonical metadata exactly once', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab({
      vaultId: 'vault:one',
      noteId: 'note:one',
      title: 'Synthetic',
      relativePath: 'note-one.md',
    })
    const before = useKnowledgeWorkspaceStore.getState()
    const tabId = before.panes['pane-1'].activeTabId!

    before.reconcileTabReference('pane-1', tabId, {
      title: 'Canonical',
      relativePath: 'pages/canonical.md',
    })
    const reconciled = useKnowledgeWorkspaceStore.getState()
    expect(reconciled.panes['pane-1'].tabs[0]).toMatchObject({
      title: 'Canonical',
      relativePath: 'pages/canonical.md',
    })
    expect(reconciled.revision).toBe(before.revision + 1)

    reconciled.reconcileTabReference('pane-1', tabId, {
      title: 'Canonical',
      relativePath: 'pages/canonical.md',
    })
    expect(useKnowledgeWorkspaceStore.getState().revision)
      .toBe(reconciled.revision)
  })

  it('refuses unsafe canonical reconciliation paths', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const before = useKnowledgeWorkspaceStore.getState()
    const tabId = before.panes['pane-1'].activeTabId!

    before.reconcileTabReference('pane-1', tabId, {
      title: 'Unsafe',
      relativePath: '../outside.md',
    })

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject(plan)
  })

  it('reconciles only a valid page unified document ID without activating another tab', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const before = useKnowledgeWorkspaceStore.getState()
    const tabId = before.panes['pane-1'].activeTabId!

    before.reconcileTabReference('pane-1', tabId, {
      title: plan.title,
      relativePath: plan.relativePath,
      knowledgeDocumentId: 'knowledge_engine_document:research',
    })

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1']).toMatchObject({
      activeTabId: tabId,
      tabs: [{ id: tabId, knowledgeDocumentId: 'knowledge_engine_document:research' }],
    })
    useKnowledgeWorkspaceStore.getState().reconcileTabReference('pane-1', tabId, {
      title: plan.title,
      relativePath: plan.relativePath,
      knowledgeDocumentId: 'not-a-unified-id',
    })
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].knowledgeDocumentId)
      .toBe('knowledge_engine_document:research')
  })

  it.each([
    { ...plan, vaultId: '' },
    { ...plan, vaultId: 'v'.repeat(129) },
    { ...plan, noteId: '' },
    { ...plan, noteId: 'n'.repeat(129) },
    { ...plan, title: '' },
    { ...plan, title: 't'.repeat(513) },
    { ...plan, relativePath: '' },
    { ...plan, relativePath: '/Users/owner/secret.md' },
    { ...plan, relativePath: 'Projects/../secret.md' },
    { ...plan, relativePath: 'p'.repeat(4097) },
    { ...plan, viewMode: 'invalid-mode' },
  ] as OpenKnowledgeTab[])('refuses an invalid open tab without changing state: $relativePath', (tab) => {
    const before = useKnowledgeWorkspaceStore.getState()

    before.openTab(tab)

    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
  })

  it('caps the workspace at 128 total tabs without creating invalid state', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    for (let index = 1; index <= 128; index += 1) {
      store.openTab({
        ...plan,
        noteId: `note:${index}`,
        relativePath: `Projects/${index}.md`,
      })
    }
    const before = useKnowledgeWorkspaceStore.getState()

    before.openTab({
      ...plan,
      noteId: 'note:129',
      relativePath: 'Projects/129.md',
    })

    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
    expect(Object.values(before.panes).flatMap((pane) => pane.tabs)).toHaveLength(128)
    expect(() => serializeKnowledgeWorkspace(before)).not.toThrow()
  })

  it('refuses a 33rd pane and keeps the workspace schema-valid', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    let sourcePaneId = 'pane-1'
    for (let count = 1; count < 32; count += 1) {
      sourcePaneId = store.splitPane(sourcePaneId, 'horizontal')
    }
    const before = useKnowledgeWorkspaceStore.getState()

    const returnedPaneId = before.splitPane(sourcePaneId, 'vertical')

    expect(returnedPaneId).toBe(sourcePaneId)
    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
    expect(selectPaneCount(before)).toBe(32)
    expect(() => serializeKnowledgeWorkspace(before)).not.toThrow()
  })

  it('refuses a split whose target is already at layout depth 64', () => {
    let layout: KnowledgeLayoutNode = { type: 'pane', paneId: 'pane-1' }
    for (let depth = 1; depth < 64; depth += 1) {
      layout = {
        type: 'split',
        id: `split-depth-${depth}`,
        direction: 'horizontal',
        firstSize: 50,
        first: layout,
        second: { type: 'pane', paneId: 'pane-1' },
      }
    }
    useKnowledgeWorkspaceStore.setState({ layout })
    const before = useKnowledgeWorkspaceStore.getState()

    const returnedPaneId = before.splitPane('pane-1', 'vertical')

    expect(returnedPaneId).toBe('pane-1')
    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
  })

  it('keeps identity and revision stable for no-op activation and view actions', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const active = useKnowledgeWorkspaceStore.getState()
    const activeTabId = active.panes['pane-1'].activeTabId!

    active.setActivePane('pane-1')
    expect(useKnowledgeWorkspaceStore.getState()).toBe(active)
    active.activateTab('pane-1', activeTabId)
    expect(useKnowledgeWorkspaceStore.getState()).toBe(active)
    active.openTab(plan)
    expect(useKnowledgeWorkspaceStore.getState()).toBe(active)
    active.setTabViewMode('pane-1', activeTabId, 'reading')
    expect(useKnowledgeWorkspaceStore.getState()).toBe(active)
    expect(useKnowledgeWorkspaceStore.getState().revision).toBe(active.revision)
  })

  it('refuses invalid runtime view-mode and split-direction inputs', () => {
    const store = useKnowledgeWorkspaceStore.getState()
    store.openTab(plan)
    const before = useKnowledgeWorkspaceStore.getState()
    const activeTabId = before.panes['pane-1'].activeTabId!

    before.setTabViewMode(
      'pane-1',
      activeTabId,
      'invalid-mode' as Parameters<typeof before.setTabViewMode>[2],
    )
    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)

    const returnedPaneId = before.splitPane(
      'pane-1',
      'diagonal' as Parameters<typeof before.splitPane>[1],
    )
    expect(returnedPaneId).toBe('pane-1')
    expect(useKnowledgeWorkspaceStore.getState()).toBe(before)
  })

  it('allocates a collision-free tab ID when nextId points at an existing tab', () => {
    useKnowledgeWorkspaceStore.getState().replaceWorkspace({
      ...defaultKnowledgeWorkspace(),
      nextId: 2,
      panes: {
        'pane-1': {
          id: 'pane-1',
          activeTabId: 'tab-2',
          tabs: [{
            id: 'tab-2',
            ...plan,
            viewMode: 'reading',
            sourceAuthority: 'external-vault',
            knowledgeDocumentId: null,
            graphViewport: { x: 0, y: 0, zoom: 1 },
          }],
        },
      },
    })

    useKnowledgeWorkspaceStore.getState().openTab(research)

    const state = useKnowledgeWorkspaceStore.getState()
    expect(state.panes['pane-1'].tabs.map((tab) => tab.id))
      .toEqual(['tab-2', 'tab-3'])
    expect(state.nextId).toBe(4)
    expect(() => serializeKnowledgeWorkspace(state)).not.toThrow()
  })

  it('allocates collision-free pane and split IDs without overwriting existing state', () => {
    useKnowledgeWorkspaceStore.getState().replaceWorkspace({
      version: 1,
      activePaneId: 'pane-1',
      nextId: 2,
      panes: {
        'pane-1': { id: 'pane-1', activeTabId: null, tabs: [] },
        'pane-2': { id: 'pane-2', activeTabId: null, tabs: [] },
      },
      layout: {
        type: 'split',
        id: 'split-4',
        direction: 'horizontal',
        firstSize: 50,
        first: { type: 'pane', paneId: 'pane-1' },
        second: { type: 'pane', paneId: 'pane-2' },
      },
      navigation: defaultKnowledgeWorkspace().navigation,
    })

    const newPaneId = useKnowledgeWorkspaceStore
      .getState().splitPane('pane-1', 'vertical')

    const state = useKnowledgeWorkspaceStore.getState()
    expect(newPaneId).toBe('pane-3')
    expect(Object.keys(state.panes).sort()).toEqual(['pane-1', 'pane-2', 'pane-3'])
    expect(JSON.stringify(state.layout)).toContain('"id":"split-5"')
    expect(state.nextId).toBe(6)
    expect(() => serializeKnowledgeWorkspace(state)).not.toThrow()
  })
})
