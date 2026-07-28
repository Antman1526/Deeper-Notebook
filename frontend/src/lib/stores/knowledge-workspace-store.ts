import { create } from 'zustand'

import {
  defaultKnowledgeWorkspace,
  type KnowledgeLayoutNode,
  type KnowledgePane,
  type KnowledgeViewMode,
  type KnowledgeWorkspaceDocument,
  type OpenKnowledgeTab,
  type SplitDirection,
} from '@/lib/api/knowledge-workspace'

export interface KnowledgeWorkspaceState extends KnowledgeWorkspaceDocument {
  hydrated: boolean
  replaceWorkspace: (document: KnowledgeWorkspaceDocument) => void
  openTab: (tab: OpenKnowledgeTab, paneId?: string) => void
  closeTab: (paneId: string, tabId: string) => void
  activateTab: (paneId: string, tabId: string) => void
  setActivePane: (paneId: string) => void
  setTabViewMode: (paneId: string, tabId: string, mode: KnowledgeViewMode) => void
  splitPane: (paneId: string, direction: SplitDirection) => string
  closePane: (paneId: string) => void
  resetWorkspace: () => void
}

let workspaceRevision = 0

export function getKnowledgeWorkspaceRevision(): number {
  return workspaceRevision
}

function markWorkspaceModified(): void {
  workspaceRevision += 1
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

export const useKnowledgeWorkspaceStore = create<KnowledgeWorkspaceState>()((set, get) => ({
  ...defaultKnowledgeWorkspace(),
  hydrated: false,

  replaceWorkspace: (document) => {
    set({ ...document, hydrated: true })
  },

  openTab: (tab, requestedPaneId) => {
    const state = get()
    const paneId = requestedPaneId ?? state.activePaneId
    const pane = state.panes[paneId]
    if (!pane) return
    const existing = pane.tabs.find(
      (candidate) => candidate.vaultId === tab.vaultId && candidate.noteId === tab.noteId,
    )
    markWorkspaceModified()
    if (existing) {
      set({
        activePaneId: paneId,
        panes: {
          ...state.panes,
          [paneId]: { ...pane, activeTabId: existing.id },
        },
      })
      return
    }

    const created = {
      ...tab,
      id: `tab-${state.nextId}`,
      viewMode: tab.viewMode ?? 'reading',
    }
    set({
      activePaneId: paneId,
      nextId: state.nextId + 1,
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
    markWorkspaceModified()
    set({
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
    markWorkspaceModified()
    set({
      activePaneId: paneId,
      panes: {
        ...state.panes,
        [paneId]: { ...pane, activeTabId: tabId },
      },
    })
  },

  setActivePane: (paneId) => {
    if (!get().panes[paneId]) return
    markWorkspaceModified()
    set({ activePaneId: paneId })
  },

  setTabViewMode: (paneId, tabId, mode) => {
    const state = get()
    const pane = state.panes[paneId]
    if (!pane?.tabs.some((tab) => tab.id === tabId)) return
    markWorkspaceModified()
    set({
      panes: {
        ...state.panes,
        [paneId]: {
          ...pane,
          tabs: pane.tabs.map((tab) => tab.id === tabId ? { ...tab, viewMode: mode } : tab),
        },
      },
    })
  },

  splitPane: (paneId, direction) => {
    const state = get()
    const sourcePane = state.panes[paneId]
    if (!sourcePane) {
      throw new Error(`Cannot split unknown pane: ${paneId}`)
    }
    const newPaneId = `pane-${state.nextId}`
    const splitId = `split-${state.nextId + 1}`
    const activeTab = sourcePane.tabs.find((tab) => tab.id === sourcePane.activeTabId)
    const newPane: KnowledgePane = {
      id: newPaneId,
      activeTabId: activeTab?.id ?? null,
      tabs: activeTab ? [{ ...activeTab }] : [],
    }
    const replacement: KnowledgeLayoutNode = {
      type: 'split',
      id: splitId,
      direction,
      first: { type: 'pane', paneId },
      second: { type: 'pane', paneId: newPaneId },
    }
    markWorkspaceModified()
    set({
      activePaneId: newPaneId,
      nextId: state.nextId + 2,
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
    markWorkspaceModified()
    set({
      panes,
      layout,
      activePaneId: state.activePaneId === paneId
        ? firstPaneId(layout)
        : state.activePaneId,
    })
  },

  resetWorkspace: () => {
    markWorkspaceModified()
    set({ ...defaultKnowledgeWorkspace(), hydrated: false })
  },
}))

export function selectActiveKnowledgeTab(state: KnowledgeWorkspaceState) {
  const pane = state.panes[state.activePaneId]
  return pane?.tabs.find((tab) => tab.id === pane.activeTabId)
}

export function selectPaneCount(state: KnowledgeWorkspaceState): number {
  return Object.keys(state.panes).length
}
