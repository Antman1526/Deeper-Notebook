import { z } from 'zod'

import apiClient from './client'

const workspacePath = '/deeper-notebook/workspace/knowledge'

export const knowledgeViewModeSchema = z.enum([
  'reading',
  'source',
  'live-preview',
  'graph',
])
export const splitDirectionSchema = z.enum(['horizontal', 'vertical'])

const relativePathSchema = z.string().min(1).max(4096).superRefine((value, context) => {
  if (/^(?:[\\/]|[A-Za-z]:)/.test(value)) {
    context.addIssue({
      code: 'custom',
      message: 'note path must be relative to its vault',
    })
  }
  if (value.split(/[\\/]/).includes('..')) {
    context.addIssue({
      code: 'custom',
      message: 'note path must not escape its vault',
    })
  }
})

export const knowledgeTabWireSchema = z.object({
  id: z.string().min(1).max(128),
  vault_id: z.string().min(1).max(128),
  note_id: z.string().min(1).max(128),
  title: z.string().min(1).max(512),
  relative_path: relativePathSchema,
  view_mode: knowledgeViewModeSchema,
}).strict()

export const knowledgePaneWireSchema = z.object({
  id: z.string().min(1).max(128),
  active_tab_id: z.string().min(1).max(128).nullable(),
  tabs: z.array(knowledgeTabWireSchema),
}).strict()

export type KnowledgeLayoutWire =
  | { type: 'pane'; pane_id: string }
  | {
      type: 'split'
      id: string
      direction: SplitDirection
      first: KnowledgeLayoutWire
      second: KnowledgeLayoutWire
    }

export const knowledgeLayoutWireSchema: z.ZodType<KnowledgeLayoutWire> = z.lazy(() =>
  z.discriminatedUnion('type', [
    z.object({
      type: z.literal('pane'),
      pane_id: z.string().min(1).max(128),
    }).strict(),
    z.object({
      type: z.literal('split'),
      id: z.string().min(1).max(128),
      direction: splitDirectionSchema,
      first: knowledgeLayoutWireSchema,
      second: knowledgeLayoutWireSchema,
    }).strict(),
  ]),
)

export const knowledgeWorkspaceWireSchema = z.object({
  version: z.literal(1),
  active_pane_id: z.string().min(1).max(128),
  next_id: z.number().int().min(1),
  panes: z.record(z.string(), knowledgePaneWireSchema),
  layout: knowledgeLayoutWireSchema,
}).strict().superRefine((document, context) => {
  const paneIds = Object.keys(document.panes)
  let totalTabs = 0

  if (paneIds.length > 32) {
    context.addIssue({ code: 'custom', message: 'workspace cannot contain more than 32 panes' })
  }

  for (const [paneKey, pane] of Object.entries(document.panes)) {
    if (paneKey !== pane.id) {
      context.addIssue({ code: 'custom', message: 'pane dictionary keys must match pane IDs' })
    }
    const tabIds = pane.tabs.map((tab) => tab.id)
    totalTabs += tabIds.length
    if (new Set(tabIds).size !== tabIds.length) {
      context.addIssue({ code: 'custom', message: 'tab IDs must be unique within each pane' })
    }
    if (pane.active_tab_id !== null && !tabIds.includes(pane.active_tab_id)) {
      context.addIssue({ code: 'custom', message: 'active tab must exist in its pane' })
    }
  }

  if (totalTabs > 128) {
    context.addIssue({ code: 'custom', message: 'workspace cannot contain more than 128 tabs' })
  }
  if (!(document.active_pane_id in document.panes)) {
    context.addIssue({ code: 'custom', message: 'active pane must exist in the workspace' })
  }

  const layoutPaneIds: string[] = []
  const splitIds = new Set<string>()
  const stack: Array<{ node: KnowledgeLayoutWire; depth: number }> = [
    { node: document.layout, depth: 1 },
  ]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (current.depth > 64) {
      context.addIssue({ code: 'custom', message: 'workspace layout cannot exceed depth 64' })
      break
    }
    if (current.node.type === 'pane') {
      layoutPaneIds.push(current.node.pane_id)
      continue
    }
    if (splitIds.has(current.node.id)) {
      context.addIssue({ code: 'custom', message: 'split IDs must be unique' })
    }
    splitIds.add(current.node.id)
    stack.push(
      { node: current.node.first, depth: current.depth + 1 },
      { node: current.node.second, depth: current.depth + 1 },
    )
  }

  if (new Set(layoutPaneIds).size !== layoutPaneIds.length) {
    context.addIssue({ code: 'custom', message: 'workspace layout cannot duplicate panes' })
  }
  if (
    layoutPaneIds.length !== paneIds.length
    || layoutPaneIds.some((paneId) => !(paneId in document.panes))
  ) {
    context.addIssue({
      code: 'custom',
      message: 'workspace layout must reference every pane exactly once',
    })
  }
})

export type KnowledgeViewMode = z.infer<typeof knowledgeViewModeSchema>
export type SplitDirection = z.infer<typeof splitDirectionSchema>

export interface KnowledgeTab {
  id: string
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode: KnowledgeViewMode
}

export interface OpenKnowledgeTab {
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode?: KnowledgeViewMode
}

export interface KnowledgePane {
  id: string
  activeTabId: string | null
  tabs: KnowledgeTab[]
}

export interface PaneLayoutNode {
  type: 'pane'
  paneId: string
}

export interface SplitLayoutNode {
  type: 'split'
  id: string
  direction: SplitDirection
  first: KnowledgeLayoutNode
  second: KnowledgeLayoutNode
}

export type KnowledgeLayoutNode = PaneLayoutNode | SplitLayoutNode

export interface KnowledgeWorkspaceDocument {
  version: 1
  activePaneId: string
  nextId: number
  panes: Record<string, KnowledgePane>
  layout: KnowledgeLayoutNode
}

export function defaultKnowledgeWorkspace(): KnowledgeWorkspaceDocument {
  return {
    version: 1,
    activePaneId: 'pane-1',
    nextId: 2,
    panes: {
      'pane-1': {
        id: 'pane-1',
        activeTabId: null,
        tabs: [],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
  }
}

function assertNoAbsolutePath(value: unknown): void {
  if (typeof value === 'string') {
    if (/^(?:[\\/]|[A-Za-z]:)/.test(value)) {
      throw new Error('Knowledge workspace contained an absolute path')
    }
    return
  }
  if (Array.isArray(value)) {
    value.forEach(assertNoAbsolutePath)
  } else if (value && typeof value === 'object') {
    Object.values(value).forEach(assertNoAbsolutePath)
  }
}

function fromWireLayout(layout: KnowledgeLayoutWire): KnowledgeLayoutNode {
  if (layout.type === 'pane') {
    return { type: 'pane', paneId: layout.pane_id }
  }
  return {
    type: 'split',
    id: layout.id,
    direction: layout.direction,
    first: fromWireLayout(layout.first),
    second: fromWireLayout(layout.second),
  }
}

function toWireLayout(layout: KnowledgeLayoutNode): KnowledgeLayoutWire {
  if (layout.type === 'pane') {
    return { type: 'pane', pane_id: layout.paneId }
  }
  return {
    type: 'split',
    id: layout.id,
    direction: layout.direction,
    first: toWireLayout(layout.first),
    second: toWireLayout(layout.second),
  }
}

function fromWire(data: unknown): KnowledgeWorkspaceDocument {
  assertNoAbsolutePath(data)
  const wire = knowledgeWorkspaceWireSchema.parse(data)
  return {
    version: wire.version,
    activePaneId: wire.active_pane_id,
    nextId: wire.next_id,
    panes: Object.fromEntries(
      Object.entries(wire.panes).map(([paneId, pane]) => [
        paneId,
        {
          id: pane.id,
          activeTabId: pane.active_tab_id,
          tabs: pane.tabs.map((tab) => ({
            id: tab.id,
            vaultId: tab.vault_id,
            noteId: tab.note_id,
            title: tab.title,
            relativePath: tab.relative_path,
            viewMode: tab.view_mode,
          })),
        },
      ]),
    ),
    layout: fromWireLayout(wire.layout),
  }
}

export function serializeKnowledgeWorkspace(document: KnowledgeWorkspaceDocument) {
  const wire = {
    version: document.version,
    active_pane_id: document.activePaneId,
    next_id: document.nextId,
    panes: Object.fromEntries(
      Object.entries(document.panes).map(([paneId, pane]) => [
        paneId,
        {
          id: pane.id,
          active_tab_id: pane.activeTabId,
          tabs: pane.tabs.map((tab) => ({
            id: tab.id,
            vault_id: tab.vaultId,
            note_id: tab.noteId,
            title: tab.title,
            relative_path: tab.relativePath,
            view_mode: tab.viewMode,
          })),
        },
      ]),
    ),
    layout: toWireLayout(document.layout),
  }
  assertNoAbsolutePath(wire)
  return knowledgeWorkspaceWireSchema.parse(wire)
}

export const knowledgeWorkspaceApi = {
  get: async (): Promise<KnowledgeWorkspaceDocument> =>
    fromWire((await apiClient.get(workspacePath)).data),
  put: async (document: KnowledgeWorkspaceDocument): Promise<KnowledgeWorkspaceDocument> =>
    fromWire((await apiClient.put(workspacePath, serializeKnowledgeWorkspace(document))).data),
}
