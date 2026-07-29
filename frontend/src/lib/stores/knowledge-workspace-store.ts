import { create } from 'zustand'

import {
  defaultKnowledgeWorkspace,
  knowledgeViewModeSchema,
  openKnowledgeTabSchema,
  serializeKnowledgeWorkspace,
  splitDirectionSchema,
  type KnowledgeLayoutNode,
  type KnowledgePane,
  type KnowledgeViewMode,
  type KnowledgeWorkspaceDocument,
  type OpenKnowledgeTab,
  type SplitDirection,
} from '@/lib/api/knowledge-workspace'

export interface KnowledgeWorkspaceState extends KnowledgeWorkspaceDocument {
  hydrated: boolean
  revision: number
  durableRevision: number
  durableFingerprint: string | null
  replaceWorkspace: (document: KnowledgeWorkspaceDocument) => void
  hydrateWorkspace: (
    document: KnowledgeWorkspaceDocument,
    requestStartRevision: number,
  ) => void
  markWorkspaceDurable: (revision: number, fingerprint: string) => void
  openTab: (tab: OpenKnowledgeTab, paneId?: string) => void
  reconcileTabReference: (
    paneId: string,
    tabId: string,
    reference: Pick<OpenKnowledgeTab, 'title' | 'relativePath'>,
  ) => void
  closeTab: (paneId: string, tabId: string) => void
  activateTab: (paneId: string, tabId: string) => void
  setActivePane: (paneId: string) => void
  setTabViewMode: (paneId: string, tabId: string, mode: KnowledgeViewMode) => void
  splitPane: (paneId: string, direction: SplitDirection) => string
  closePane: (paneId: string) => void
  resetWorkspace: () => void
}

export function getKnowledgeWorkspaceRevision(): number {
  return useKnowledgeWorkspaceStore.getState().revision
}

function replacePaneInLayout(
  node: KnowledgeLayoutNode,
  paneId: string,
  replacement: KnowledgeLayoutNode,
): KnowledgeLayoutNode {
  if (node.type === 'pane') {
    return node.paneId === paneId ? replacement : node
  }
  return {
    ...node,
    first: replacePaneInLayout(node.first, paneId, replacement),
    second: replacePaneInLayout(node.second, paneId, replacement),
  }
}

function collapsePane(
  node: KnowledgeLayoutNode,
  paneId: string,
): KnowledgeLayoutNode | null {
  if (node.type === 'pane') {
    return node.paneId === paneId ? null : node
  }
  const first = collapsePane(node.first, paneId)
  const second = collapsePane(node.second, paneId)
  if (!first) return second
  if (!second) return first
  if (first === node.first && second === node.second) return node
  return { ...node, first, second }
}

function firstPaneId(node: KnowledgeLayoutNode): string {
  return node.type === 'pane' ? node.paneId : firstPaneId(node.first)
}

function totalTabCount(panes: Record<string, KnowledgePane>): number {
  return Object.values(panes).reduce((total, pane) => total + pane.tabs.length, 0)
}

function deepestPaneOccurrence(node: KnowledgeLayoutNode, paneId: string): number {
  const stack: Array<{ node: KnowledgeLayoutNode; depth: number }> = [{ node, depth: 1 }]
  let deepest = 0
  let visitedNodes = 0
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    visitedNodes += 1
    if (visitedNodes > 10_000) return Number.POSITIVE_INFINITY
    if (current.node.type === 'pane') {
      if (current.node.paneId === paneId) deepest = Math.max(deepest, current.depth)
      continue
    }
    stack.push(
      { node: current.node.first, depth: current.depth + 1 },
      { node: current.node.second, depth: current.depth + 1 },
    )
  }
  return deepest
}

function collectTabIds(panes: Record<string, KnowledgePane>): Set<string> {
  return new Set(
    Object.values(panes).flatMap((pane) => pane.tabs.map((tab) => tab.id)),
  )
}

function collectSplitIds(layout: KnowledgeLayoutNode): Set<string> {
  const ids = new Set<string>()
  const stack = [layout]
  while (stack.length > 0) {
    const node = stack.pop()
    if (!node || node.type === 'pane') continue
    ids.add(node.id)
    stack.push(node.first, node.second)
  }
  return ids
}

function allocateId(
  prefix: 'tab' | 'pane' | 'split',
  startingId: number,
  usedIds: Set<string>,
): { id: string; nextId: number } {
  let candidate = startingId
  while (usedIds.has(`${prefix}-${candidate}`)) candidate += 1
  return { id: `${prefix}-${candidate}`, nextId: candidate + 1 }
}

function workspaceFingerprint(document: KnowledgeWorkspaceDocument): string | null {
  try {
    return JSON.stringify(serializeKnowledgeWorkspace(document))
  } catch {
    return null
  }
}

export const useKnowledgeWorkspaceStore = create<KnowledgeWorkspaceState>()((set, get) => ({
  ...defaultKnowledgeWorkspace(),
  hydrated: false,
  revision: 0,
  durableRevision: 0,
  durableFingerprint: workspaceFingerprint(defaultKnowledgeWorkspace()),

  replaceWorkspace: (document) => {
    const fingerprint = workspaceFingerprint(document)
    if (!fingerprint) return
    const state = get()
    set({
      ...document,
      hydrated: true,
      durableRevision: state.revision,
      durableFingerprint: fingerprint,
    })
  },

  hydrateWorkspace: (document, requestStartRevision) => {
    const fingerprint = workspaceFingerprint(document)
    if (!fingerprint) return
    const state = get()
    if (state.revision === requestStartRevision) {
      set({
        ...document,
        hydrated: true,
        durableRevision: Math.max(state.durableRevision, requestStartRevision),
        durableFingerprint: fingerprint,
      })
      return
    }
    if (!state.hydrated || state.durableRevision < requestStartRevision) {
      set({
        hydrated: true,
        durableRevision: Math.max(state.durableRevision, requestStartRevision),
        durableFingerprint: fingerprint,
      })
    }
  },

  markWorkspaceDurable: (revision, fingerprint) => {
    const state = get()
    const durableRevision = Math.min(revision, state.revision)
    if (
      durableRevision < state.durableRevision
      || (
        durableRevision === state.durableRevision
        && fingerprint === state.durableFingerprint
      )
    ) {
      return
    }
    set({ durableRevision, durableFingerprint: fingerprint })
  },

  openTab: (tab, requestedPaneId) => {
    const parsed = openKnowledgeTabSchema.safeParse(tab)
    if (!parsed.success) return
    const validTab = parsed.data
    const state = get()
    const paneId = requestedPaneId ?? state.activePaneId
    const pane = state.panes[paneId]
    if (!pane) return
    const existing = pane.tabs.find(
      (candidate) =>
        candidate.vaultId === validTab.vaultId && candidate.noteId === validTab.noteId,
    )
    if (existing) {
      if (state.activePaneId === paneId && pane.activeTabId === existing.id) return
      set({
        activePaneId: paneId,
        revision: state.revision + 1,
        panes: {
          ...state.panes,
          [paneId]: { ...pane, activeTabId: existing.id },
        },
      })
      return
    }
    if (totalTabCount(state.panes) >= 128) return

    const allocated = allocateId('tab', state.nextId, collectTabIds(state.panes))
    const created = {
      ...validTab,
      id: allocated.id,
      viewMode: validTab.viewMode ?? 'reading',
    }
    set({
      activePaneId: paneId,
      nextId: allocated.nextId,
      revision: state.revision + 1,
      panes: {
        ...state.panes,
        [paneId]: {
          ...pane,
          activeTabId: created.id,
          tabs: [...pane.tabs, created],
        },
      },
    })
  },

  reconcileTabReference: (paneId, tabId, reference) => {
    const state = get()
    const pane = state.panes[paneId]
    const tab = pane?.tabs.find((candidate) => candidate.id === tabId)
    if (!pane || !tab) return
    const parsed = openKnowledgeTabSchema.safeParse({
      vaultId: tab.vaultId,
      noteId: tab.noteId,
      title: reference.title,
      relativePath: reference.relativePath,
      viewMode: tab.viewMode,
    })
    if (!parsed.success) return
    if (
      tab.title === parsed.data.title
      && tab.relativePath === parsed.data.relativePath
    ) {
      return
    }
    set({
      revision: state.revision + 1,
      panes: {
        ...state.panes,
        [paneId]: {
          ...pane,
          tabs: pane.tabs.map((candidate) => candidate.id === tabId
            ? {
                ...candidate,
                title: parsed.data.title,
                relativePath: parsed.data.relativePath,
              }
            : candidate),
        },
      },
    })
  },

  closeTab: (paneId, tabId) => {
    const state = get()
    const pane = state.panes[paneId]
    const closedIndex = pane?.tabs.findIndex((tab) => tab.id === tabId) ?? -1
    if (!pane || closedIndex < 0) return
    const tabs = pane.tabs.filter((tab) => tab.id !== tabId)
    let activeTabId = pane.activeTabId
    if (activeTabId === tabId) {
      activeTabId = tabs[closedIndex]?.id ?? tabs[closedIndex - 1]?.id ?? null
    }
    set({
      revision: state.revision + 1,
      panes: {
        ...state.panes,
        [paneId]: { ...pane, activeTabId, tabs },
      },
    })
  },

  activateTab: (paneId, tabId) => {
    const state = get()
    const pane = state.panes[paneId]
    if (!pane?.tabs.some((tab) => tab.id === tabId)) return
    if (state.activePaneId === paneId && pane.activeTabId === tabId) return
    set({
      activePaneId: paneId,
      revision: state.revision + 1,
      panes: {
        ...state.panes,
        [paneId]: { ...pane, activeTabId: tabId },
      },
    })
  },

  setActivePane: (paneId) => {
    const state = get()
    if (!state.panes[paneId] || state.activePaneId === paneId) return
    set({ activePaneId: paneId, revision: state.revision + 1 })
  },

  setTabViewMode: (paneId, tabId, mode) => {
    const parsedMode = knowledgeViewModeSchema.safeParse(mode)
    if (!parsedMode.success) return
    const state = get()
    const pane = state.panes[paneId]
    const tab = pane?.tabs.find((candidate) => candidate.id === tabId)
    if (!pane || !tab || tab.viewMode === parsedMode.data) return
    set({
      revision: state.revision + 1,
      panes: {
        ...state.panes,
        [paneId]: {
          ...pane,
          tabs: pane.tabs.map((candidate) =>
            candidate.id === tabId
              ? { ...candidate, viewMode: parsedMode.data }
              : candidate),
        },
      },
    })
  },

  splitPane: (paneId, direction) => {
    const parsedDirection = splitDirectionSchema.safeParse(direction)
    if (!parsedDirection.success) return paneId
    const state = get()
    const sourcePane = state.panes[paneId]
    if (!sourcePane) {
      throw new Error(`Cannot split unknown pane: ${paneId}`)
    }
    const targetDepth = deepestPaneOccurrence(state.layout, paneId)
    if (
      Object.keys(state.panes).length >= 32
      || targetDepth === 0
      || targetDepth >= 64
    ) {
      return paneId
    }
    const allocatedPane = allocateId(
      'pane',
      state.nextId,
      new Set(Object.keys(state.panes)),
    )
    const allocatedSplit = allocateId(
      'split',
      allocatedPane.nextId,
      collectSplitIds(state.layout),
    )
    const newPaneId = allocatedPane.id
    const splitId = allocatedSplit.id
    const activeTab = sourcePane.tabs.find((tab) => tab.id === sourcePane.activeTabId)
    if (activeTab && totalTabCount(state.panes) >= 128) return paneId
    const newPane: KnowledgePane = {
      id: newPaneId,
      activeTabId: activeTab?.id ?? null,
      tabs: activeTab ? [{ ...activeTab }] : [],
    }
    const replacement: KnowledgeLayoutNode = {
      type: 'split',
      id: splitId,
      direction: parsedDirection.data,
      first: { type: 'pane', paneId },
      second: { type: 'pane', paneId: newPaneId },
    }
    set({
      activePaneId: newPaneId,
      nextId: allocatedSplit.nextId,
      revision: state.revision + 1,
      panes: { ...state.panes, [newPaneId]: newPane },
      layout: replacePaneInLayout(state.layout, paneId, replacement),
    })
    return newPaneId
  },

  closePane: (paneId) => {
    const state = get()
    if (!state.panes[paneId] || Object.keys(state.panes).length === 1) return
    const layout = collapsePane(state.layout, paneId)
    if (!layout) return
    const panes = { ...state.panes }
    delete panes[paneId]
    set({
      panes,
      layout,
      revision: state.revision + 1,
      activePaneId: state.activePaneId === paneId
        ? firstPaneId(layout)
        : state.activePaneId,
    })
  },

  resetWorkspace: () => {
    const revision = get().revision + 1
    const document = defaultKnowledgeWorkspace()
    set({
      ...document,
      hydrated: false,
      revision,
      durableRevision: revision,
      durableFingerprint: workspaceFingerprint(document),
    })
  },
}))

export function selectActiveKnowledgeTab(state: KnowledgeWorkspaceState) {
  const pane = state.panes[state.activePaneId]
  return pane?.tabs.find((tab) => tab.id === pane.activeTabId)
}

export function selectPaneCount(state: KnowledgeWorkspaceState): number {
  return Object.keys(state.panes).length
}
