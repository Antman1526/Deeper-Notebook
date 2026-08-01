import { z } from 'zod'

import apiClient from './client'

const workspacePath = '/deeper-notebook/workspace/knowledge'

export const knowledgeViewModeSchema = z.enum([
  'reading',
  'source',
  'live-preview',
  'graph',
  'canvas',
])
export const splitDirectionSchema = z.enum(['horizontal', 'vertical'])
export const knowledgeSourceAuthoritySchema = z.enum([
  'external-vault',
  'overlay',
])
export const knowledgeAuthorityFilterSchema = z.enum([
  'app_owned',
  'external_read_only',
])
export const graphViewportSchema = z.object({
  x: z.number().finite(),
  y: z.number().finite(),
  zoom: z.number().finite().min(0.1).max(10),
}).strict()
export const knowledgeWorkspaceNavigationWireSchema = z.object({
  utility_mode: z.enum(['sources', 'bookmarks', 'workspaces']).default('sources'),
  sidebar_visible: z.boolean().default(true),
  sidebar_width: z.number().int().min(240).max(640).default(320),
  active_bookmark_folder_id: z.string().min(1).max(128).nullable().default(null),
  bookmark_tags: z.array(z.string().min(1).max(128)).max(32).default([]),
  source_tree_query: z.string().max(256).default(''),
  search_query: z.string().max(512).default(''),
  search_mode: z.enum(['exact', 'text', 'semantic']).default('text'),
  active_draft_id: z.string().min(1).max(128).nullable().default(null),
  selected_space_ids: z.array(z.string().regex(/^knowledge_engine_space:[A-Za-z0-9_-]+$/)).max(32).default([]),
  authority_filters: z.array(knowledgeAuthorityFilterSchema).max(2).default([]),
  metrics_visible: z.boolean().default(true),
}).strict().default({
  utility_mode: 'sources', sidebar_visible: true, sidebar_width: 320,
  active_bookmark_folder_id: null, bookmark_tags: [], source_tree_query: '',
  search_query: '', search_mode: 'text', active_draft_id: null, selected_space_ids: [],
  authority_filters: [], metrics_visible: true,
})

export const canonicalVaultRelativePathSchema = z.string()
  .min(1)
  .max(4096)
  .superRefine((value, context) => {
    const segments = value.split('/')
    if (
      !value
      || value.trim() !== value
      || value.startsWith('/')
      || /^[A-Za-z]:/.test(value)
      || value.includes('\\')
      || value.includes('\0')
      || segments.some((segment) =>
        !segment || segment === '.' || segment === '..')
    ) {
      context.addIssue({
        code: 'custom',
        message: 'value must be a canonical vault-relative path',
      })
    }
  })

export const openKnowledgeTabSchema = z.object({
  vaultId: z.string().min(1).max(128),
  noteId: z.string().min(1).max(128),
  title: z.string().min(1).max(512),
  relativePath: canonicalVaultRelativePathSchema,
  viewMode: knowledgeViewModeSchema.optional(),
  sourceAuthority: knowledgeSourceAuthoritySchema.optional(),
  knowledgeDocumentId: z.string().regex(/^knowledge_engine_document:[A-Za-z0-9_-]+$/).nullable().optional(),
  graphViewport: graphViewportSchema.nullable().optional(),
}).strict()

export const knowledgeTabWireSchema = z.object({
  id: z.string().min(1).max(128),
  vault_id: z.string().min(1).max(128),
  note_id: z.string().min(1).max(128),
  title: z.string().min(1).max(512),
  relative_path: canonicalVaultRelativePathSchema,
  view_mode: knowledgeViewModeSchema,
  source_authority: knowledgeSourceAuthoritySchema.default('external-vault'),
  knowledge_document_id: z.string().regex(/^knowledge_engine_document:[A-Za-z0-9_-]+$/).nullable().default(null),
  graph_viewport: graphViewportSchema.nullable().default({ x: 0, y: 0, zoom: 1 }),
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
      first_size: number
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
      first_size: z.number().finite().min(10).max(90).default(50),
      first: knowledgeLayoutWireSchema,
      second: knowledgeLayoutWireSchema,
    }).strict(),
  ]),
)

const rawKnowledgeWorkspaceV1WireSchema = z.object({
  version: z.literal(1),
  active_pane_id: z.string().min(1).max(128),
  next_id: z.number().int().min(1),
  panes: z.record(z.string(), knowledgePaneWireSchema),
  layout: knowledgeLayoutWireSchema,
  navigation: knowledgeWorkspaceNavigationWireSchema,
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

export const researchModeSchema = z.enum(['read', 'write', 'ask', 'search', 'graph', 'podcast'])
const documentTabTargetWireSchema = z.object({
  kind: z.literal('document'), container_id: z.string().min(1).max(128),
  note_id: z.string().min(1).max(128), title: z.string().min(1).max(512),
  relative_locator: canonicalVaultRelativePathSchema,
  authority: knowledgeSourceAuthoritySchema,
  knowledge_document_id: z.string().max(128).nullable().default(null),
  render_mode: z.enum(['reading', 'source', 'live-preview', 'canvas']).default('reading'),
}).strict()
const workspaceTabTargetWireSchema = z.discriminatedUnion('kind', [
  documentTabTargetWireSchema,
  z.object({ kind: z.literal('ask'), thread_id: z.string().max(128).nullable().default(null), selected_document_ids: z.array(z.string()).max(128).default([]) }).strict(),
  z.object({ kind: z.literal('search'), query: z.string().max(512).default(''), search_mode: z.enum(['exact', 'text', 'semantic']).default('text'), space_ids: z.array(z.string()).max(32).default([]), authority_kinds: z.array(knowledgeAuthorityFilterSchema).max(2).default([]) }).strict(),
  z.object({ kind: z.literal('graph'), root_document_id: z.string().max(128).nullable().default(null), space_ids: z.array(z.string()).max(32).default([]), relation_kinds: z.array(z.string()).max(32).default([]), viewport: graphViewportSchema.default({ x: 0, y: 0, zoom: 1 }), origin: documentTabTargetWireSchema.nullable().default(null) }).strict(),
  z.object({ kind: z.literal('podcast'), production_id: z.string().max(128).nullable().default(null), seed_document_ids: z.array(z.string()).max(128).default([]) }).strict(),
])
const knowledgeTabV2WireSchema = z.object({ id: z.string().min(1).max(128), mode: researchModeSchema, title: z.string().min(1).max(512), target: workspaceTabTargetWireSchema }).strict()
const rawKnowledgeWorkspaceV2WireSchema = z.object({
  version: z.literal(2), active_pane_id: z.string().min(1).max(128), next_id: z.number().int().min(1),
  panes: z.record(z.string(), z.object({ id: z.string().min(1).max(128), active_tab_id: z.string().min(1).max(128).nullable(), tabs: z.array(knowledgeTabV2WireSchema) }).strict()),
  layout: knowledgeLayoutWireSchema, navigation: knowledgeWorkspaceNavigationWireSchema,
}).strict().superRefine((document, context) => {
  const paneIds = Object.keys(document.panes)
  let totalTabs = 0
  for (const [paneId, pane] of Object.entries(document.panes)) {
    if (pane.id !== paneId) context.addIssue({ code: 'custom', message: 'pane dictionary keys must match pane IDs' })
    const tabIds = pane.tabs.map((tab) => tab.id)
    totalTabs += tabIds.length
    if (new Set(tabIds).size !== tabIds.length) context.addIssue({ code: 'custom', message: 'tab IDs must be unique within each pane' })
    if (pane.active_tab_id !== null && !tabIds.includes(pane.active_tab_id)) context.addIssue({ code: 'custom', message: 'active tab must exist in its pane' })
  }
  if (totalTabs > 128) context.addIssue({ code: 'custom', message: 'workspace cannot contain more than 128 tabs' })
  if (!paneIds.includes(document.active_pane_id)) context.addIssue({ code: 'custom', message: 'active pane must exist in the workspace' })
  const layoutPanes: string[] = []
  const splitIds = new Set<string>()
  const stack: KnowledgeLayoutWire[] = [document.layout]
  while (stack.length) {
    const node = stack.pop()!
    if (node.type === 'pane') layoutPanes.push(node.pane_id)
    else {
      if (splitIds.has(node.id)) context.addIssue({ code: 'custom', message: 'split IDs must be unique' })
      splitIds.add(node.id); stack.push(node.first, node.second)
    }
  }
  if (new Set(layoutPanes).size !== layoutPanes.length || layoutPanes.length !== paneIds.length || layoutPanes.some((id) => !paneIds.includes(id))) context.addIssue({ code: 'custom', message: 'workspace layout must reference every pane exactly once' })
  for (const pane of Object.values(document.panes)) for (const tab of pane.tabs) {
    const expected = { read: 'document', write: 'document', ask: 'ask', search: 'search', graph: 'graph', podcast: 'podcast' }[tab.mode]
    if (tab.target.kind !== expected || (tab.mode === 'write' && (tab.target.kind !== 'document' || tab.target.authority !== 'overlay'))) context.addIssue({ code: 'custom', message: 'workspace_mode_target_mismatch' })
  }
})

function preflightWorkspaceBounds(value: unknown, context: z.RefinementCtx): void {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return
  const document = value as Record<string, unknown>
  const panes = document.panes
  if (panes && typeof panes === 'object' && !Array.isArray(panes)) {
    const paneValues = Object.values(panes)
    if (paneValues.length > 32) {
      context.addIssue({
        code: 'custom',
        fatal: true,
        path: ['panes'],
        message: 'workspace cannot contain more than 32 panes',
      })
      return
    }
    let totalTabs = 0
    for (const pane of paneValues) {
      if (!pane || typeof pane !== 'object' || Array.isArray(pane)) continue
      const tabs = (pane as Record<string, unknown>).tabs
      if (!Array.isArray(tabs)) continue
      totalTabs += tabs.length
      if (totalTabs > 128) {
        context.addIssue({
          code: 'custom',
          fatal: true,
          path: ['panes'],
          message: 'workspace cannot contain more than 128 tabs',
        })
        return
      }
    }
  }

  const layout = document.layout
  const stack: Array<{ node: unknown; depth: number }> = [{ node: layout, depth: 1 }]

  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (current.depth > 64) {
      context.addIssue({
        code: 'custom',
        fatal: true,
        path: ['layout'],
        message: 'workspace layout cannot exceed depth 64',
      })
      return
    }
    if (!current.node || typeof current.node !== 'object' || Array.isArray(current.node)) {
      continue
    }
    const node = current.node as Record<string, unknown>
    if (node.type === 'split') {
      stack.push(
        { node: node.first, depth: current.depth + 1 },
        { node: node.second, depth: current.depth + 1 },
      )
    }
  }
}

const knowledgeWorkspacePreflightSchema = z.unknown()
  .superRefine(preflightWorkspaceBounds)

export const knowledgeWorkspaceWireSchema = knowledgeWorkspacePreflightSchema
  .pipe(z.union([rawKnowledgeWorkspaceV1WireSchema, rawKnowledgeWorkspaceV2WireSchema]))

export type KnowledgeViewMode = z.infer<typeof knowledgeViewModeSchema>
export type SplitDirection = z.infer<typeof splitDirectionSchema>
export type KnowledgeSourceAuthority = z.infer<typeof knowledgeSourceAuthoritySchema>

export interface KnowledgeTab {
  id: string
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode: KnowledgeViewMode
  sourceAuthority: KnowledgeSourceAuthority
  knowledgeDocumentId: string | null
  graphViewport: GraphViewport | null
  mode?: z.infer<typeof researchModeSchema>
  target?: z.infer<typeof workspaceTabTargetWireSchema>
  // Restore-only stable graph metadata. It is intentionally not written to the
  // Current Session wire payload, which remains compatible with the server API.
  graphBookmarkContext?: {
    rootDocumentId: string
    spaceIds: string[]
    relationKinds: string[]
    viewport: GraphViewport
  } | null
}

export interface OpenKnowledgeTab {
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode?: KnowledgeViewMode
  sourceAuthority?: KnowledgeSourceAuthority
  knowledgeDocumentId?: string | null
  graphViewport?: GraphViewport | null
  graphBookmarkContext?: KnowledgeTab['graphBookmarkContext']
}

export type GraphViewport = z.infer<typeof graphViewportSchema>
export interface KnowledgeWorkspaceNavigation {
  utilityMode: 'sources' | 'bookmarks' | 'workspaces'
  sidebarVisible: boolean
  sidebarWidth: number
  activeBookmarkFolderId: string | null
  bookmarkTags: string[]
  sourceTreeQuery: string
  searchQuery: string
  searchMode: 'exact' | 'text' | 'semantic'
  activeDraftId: string | null
  selectedSpaceIds: string[]
  authorityFilters: z.infer<typeof knowledgeAuthorityFilterSchema>[]
  metricsVisible: boolean
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
  firstSize: number
  first: KnowledgeLayoutNode
  second: KnowledgeLayoutNode
}

export type KnowledgeLayoutNode = PaneLayoutNode | SplitLayoutNode

export interface KnowledgeWorkspaceDocument {
  version: 1 | 2
  activePaneId: string
  nextId: number
  panes: Record<string, KnowledgePane>
  layout: KnowledgeLayoutNode
  navigation: KnowledgeWorkspaceNavigation
}

export function defaultKnowledgeWorkspace(): KnowledgeWorkspaceDocument {
  return {
    version: 2,
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
    navigation: {
      utilityMode: 'sources', sidebarVisible: true, sidebarWidth: 320,
      activeBookmarkFolderId: null, bookmarkTags: [], sourceTreeQuery: '',
      searchQuery: '', searchMode: 'text', activeDraftId: null, selectedSpaceIds: [],
      authorityFilters: [], metricsVisible: true,
    },
  }
}

function assertNoAbsolutePath(value: unknown): void {
  const stack: unknown[] = [value]
  const visited = new WeakSet<object>()
  while (stack.length > 0) {
    const current = stack.pop()
    if (typeof current === 'string') {
      if (/^(?:[\\/]|[A-Za-z]:)/.test(current)) {
        throw new Error('Knowledge workspace contained an absolute path')
      }
      continue
    }
    if (!current || typeof current !== 'object') continue
    if (visited.has(current)) continue
    visited.add(current)
    if (Array.isArray(current)) {
      for (const item of current) stack.push(item)
    } else {
      for (const item of Object.values(current)) stack.push(item)
    }
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
    firstSize: layout.first_size,
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
    first_size: layout.firstSize ?? 50,
    first: toWireLayout(layout.first),
    second: toWireLayout(layout.second),
  }
}

function preflightCamelLayout(layout: unknown): void {
  const stack: Array<{ node: unknown; depth: number }> = [{ node: layout, depth: 1 }]
  const visited = new WeakSet<object>()
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (current.depth > 64) {
      throw new Error('workspace layout cannot exceed depth 64')
    }
    if (!current.node || typeof current.node !== 'object' || Array.isArray(current.node)) {
      throw new Error('workspace layout has an invalid shape')
    }
    if (visited.has(current.node)) {
      throw new Error('workspace layout cannot contain cycles or shared nodes')
    }
    visited.add(current.node)
    const node = current.node as Record<string, unknown>
    if (node.type === 'pane') continue
    if (node.type !== 'split') {
      throw new Error('workspace layout has an invalid shape')
    }
    stack.push(
      { node: node.first, depth: current.depth + 1 },
      { node: node.second, depth: current.depth + 1 },
    )
  }
}

function preflightCamelWorkspace(document: KnowledgeWorkspaceDocument): void {
  const panes = Object.values(document.panes)
  if (panes.length > 32) {
    throw new Error('workspace cannot contain more than 32 panes')
  }
  let totalTabs = 0
  for (const pane of panes) {
    totalTabs += pane.tabs.length
    if (totalTabs > 128) {
      throw new Error('workspace cannot contain more than 128 tabs')
    }
  }
}

export function migrateKnowledgeWorkspaceV1(data: unknown): KnowledgeWorkspaceDocument {
  knowledgeWorkspacePreflightSchema.parse(data)
  assertNoAbsolutePath(data)
  const wire = rawKnowledgeWorkspaceV1WireSchema.parse(data)
  return {
    version: 2,
    activePaneId: wire.active_pane_id,
    nextId: wire.next_id,
    navigation: {
      utilityMode: wire.navigation.utility_mode,
      sidebarVisible: wire.navigation.sidebar_visible,
      sidebarWidth: wire.navigation.sidebar_width,
      activeBookmarkFolderId: wire.navigation.active_bookmark_folder_id,
      bookmarkTags: wire.navigation.bookmark_tags,
      sourceTreeQuery: wire.navigation.source_tree_query,
      searchQuery: wire.navigation.search_query,
      searchMode: wire.navigation.search_mode,
      activeDraftId: wire.navigation.active_draft_id,
      selectedSpaceIds: wire.navigation.selected_space_ids,
      authorityFilters: wire.navigation.authority_filters,
      metricsVisible: wire.navigation.metrics_visible,
    },
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
            sourceAuthority: tab.source_authority,
            knowledgeDocumentId: tab.knowledge_document_id,
            graphViewport: tab.graph_viewport,
            mode: tab.view_mode === 'graph' ? 'graph' : tab.source_authority === 'overlay' ? 'write' : 'read',
            target: tab.view_mode === 'graph'
              ? { kind: 'graph', root_document_id: tab.knowledge_document_id, space_ids: [], relation_kinds: [], viewport: tab.graph_viewport ?? { x: 0, y: 0, zoom: 1 }, origin: { kind: 'document', container_id: tab.vault_id, note_id: tab.note_id, title: tab.title, relative_locator: tab.relative_path, authority: tab.source_authority, knowledge_document_id: tab.knowledge_document_id, render_mode: 'reading' } }
              : { kind: 'document', container_id: tab.vault_id, note_id: tab.note_id, title: tab.title, relative_locator: tab.relative_path, authority: tab.source_authority, knowledge_document_id: tab.knowledge_document_id, render_mode: tab.view_mode },
          })),
        },
      ]),
    ),
    layout: fromWireLayout(wire.layout),
  }
}

function fromWire(data: unknown): KnowledgeWorkspaceDocument {
  knowledgeWorkspacePreflightSchema.parse(data)
  assertNoAbsolutePath(data)
  if ((data as { version?: unknown }).version === 1) return migrateKnowledgeWorkspaceV1(data)
  const wire = rawKnowledgeWorkspaceV2WireSchema.parse(data)
  return {
    version: 2, activePaneId: wire.active_pane_id, nextId: wire.next_id,
    navigation: { utilityMode: wire.navigation.utility_mode, sidebarVisible: wire.navigation.sidebar_visible, sidebarWidth: wire.navigation.sidebar_width, activeBookmarkFolderId: wire.navigation.active_bookmark_folder_id, bookmarkTags: wire.navigation.bookmark_tags, sourceTreeQuery: wire.navigation.source_tree_query, searchQuery: wire.navigation.search_query, searchMode: wire.navigation.search_mode, activeDraftId: wire.navigation.active_draft_id, selectedSpaceIds: wire.navigation.selected_space_ids, authorityFilters: wire.navigation.authority_filters, metricsVisible: wire.navigation.metrics_visible },
    panes: Object.fromEntries(Object.entries(wire.panes).map(([paneId, pane]) => [paneId, { id: pane.id, activeTabId: pane.active_tab_id, tabs: pane.tabs.map((tab) => {
      const target = tab.target
      const document = target.kind === 'document'
        ? target
        : target.kind === 'graph'
          ? target.origin
          : null
      return { id: tab.id, mode: tab.mode, target, title: tab.title, vaultId: document?.container_id ?? '', noteId: document?.note_id ?? '', relativePath: document?.relative_locator ?? '', viewMode: target.kind === 'graph' ? 'graph' : document?.render_mode ?? 'reading', sourceAuthority: document?.authority ?? 'external-vault', knowledgeDocumentId: document?.knowledge_document_id ?? (target.kind === 'graph' ? target.root_document_id : null), graphViewport: target.kind === 'graph' ? target.viewport : null }
    }) }])), layout: fromWireLayout(wire.layout),
  }
}

export function parseKnowledgeWorkspace(data: unknown): KnowledgeWorkspaceDocument {
  return fromWire(data)
}

export function serializeKnowledgeWorkspace(document: KnowledgeWorkspaceDocument) {
  preflightCamelWorkspace(document)
  preflightCamelLayout(document.layout)
  const navigation: KnowledgeWorkspaceNavigation = document.navigation ?? {
    utilityMode: 'sources', sidebarVisible: true, sidebarWidth: 320,
    activeBookmarkFolderId: null, bookmarkTags: [], sourceTreeQuery: '',
    searchQuery: '', searchMode: 'text', activeDraftId: null, selectedSpaceIds: [],
    authorityFilters: [], metricsVisible: true,
  }
  const wire = {
    version: document.version,
    active_pane_id: document.activePaneId,
    next_id: document.nextId,
    navigation: {
      utility_mode: navigation.utilityMode,
      sidebar_visible: navigation.sidebarVisible,
      sidebar_width: navigation.sidebarWidth,
      active_bookmark_folder_id: navigation.activeBookmarkFolderId,
      bookmark_tags: navigation.bookmarkTags,
      source_tree_query: navigation.sourceTreeQuery,
      search_query: navigation.searchQuery,
      search_mode: navigation.searchMode,
      active_draft_id: navigation.activeDraftId,
      selected_space_ids: navigation.selectedSpaceIds,
      authority_filters: navigation.authorityFilters,
      metrics_visible: navigation.metricsVisible,
    },
    panes: Object.fromEntries(
      Object.entries(document.panes).map(([paneId, pane]) => [
        paneId,
        {
          id: pane.id,
          active_tab_id: pane.activeTabId,
          tabs: pane.tabs.map((tab) => {
            const legacyMode = tab.viewMode === 'graph'
              ? 'graph' as const
              : tab.sourceAuthority === 'overlay' ? 'write' as const : 'read' as const
            const target = tab.target ?? (legacyMode === 'graph'
              ? {
                  kind: 'graph' as const,
                  root_document_id: tab.knowledgeDocumentId ?? null,
                  space_ids: [], relation_kinds: [],
                  viewport: tab.graphViewport ?? { x: 0, y: 0, zoom: 1 },
                  origin: {
                    kind: 'document' as const, container_id: tab.vaultId,
                    note_id: tab.noteId, title: tab.title,
                    relative_locator: tab.relativePath,
                    authority: tab.sourceAuthority,
                    knowledge_document_id: tab.knowledgeDocumentId ?? null,
                    render_mode: 'reading' as const,
                  },
                }
              : {
                  kind: 'document' as const, container_id: tab.vaultId,
                  note_id: tab.noteId, title: tab.title,
                  relative_locator: tab.relativePath,
                  authority: tab.sourceAuthority,
                  knowledge_document_id: tab.knowledgeDocumentId ?? null,
                  render_mode: tab.viewMode === 'graph' ? 'reading' as const : tab.viewMode,
                })
            return { id: tab.id, mode: tab.mode ?? legacyMode, title: tab.title, target }
          }),
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
