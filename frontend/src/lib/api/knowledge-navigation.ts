import { z } from 'zod'

import apiClient from './client'
import {
  graphViewportSchema,
  knowledgeLayoutWireSchema,
  knowledgeWorkspaceNavigationWireSchema,
  knowledgeViewModeSchema,
  type GraphViewport,
  type KnowledgeLayoutNode,
  type KnowledgeViewMode,
  type KnowledgeWorkspaceNavigation,
} from './knowledge-workspace'

const navigationPath = '/deeper-notebook/knowledge'
const allocatorWorkspaceId = 'named_knowledge_workspace:capacity_allocator'
const engineId = (prefix: string) => z.string()
  .regex(new RegExp(`^${prefix}:[A-Za-z0-9_-]+$`))
  .max(128)
const navigationId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/)
const operationId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$/)
const bookmarkId = engineId('knowledge_bookmark')
const folderId = engineId('knowledge_bookmark_folder')
const documentId = engineId('knowledge_engine_document')
const blockId = engineId('knowledge_engine_block')
const revisionId = engineId('knowledge_engine_(?:revision|source_revision)')
const spaceId = engineId('knowledge_engine_space')
const workspaceId = engineId('named_knowledge_workspace')
const publicWorkspaceId = workspaceId.refine(
  (value) => value !== allocatorWorkspaceId,
  'workspace ID is reserved',
)
const authoritySchema = z.enum(['app_owned', 'external_read_only'])
const targetStateSchema = z.enum(['available', 'stale', 'unavailable', 'missing'])
const targetKindSchema = z.enum(['document', 'block', 'search', 'graph', 'workspace'])
const dateTimeSchema = z.string().datetime({ offset: true })

type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject
interface JsonObject { [key: string]: JsonValue }

export type KnowledgeAuthority = z.infer<typeof authoritySchema>
export type KnowledgeTargetState = z.infer<typeof targetStateSchema>
export type KnowledgeTargetKind = z.infer<typeof targetKindSchema>

export interface KnowledgeOpenDescriptor {
  documentId: string
  spaceId: string
  authorityKind: KnowledgeAuthority
  sourceKind: 'overlay' | 'obsidian' | 'logseq' | 'markdown'
  title: string
  relativeLocator: string
  legacyNoteId: string
  legacyContainerId: string
}

export type KnowledgeTarget =
  | { kind: 'document'; documentId: string }
  | {
      kind: 'block'
      documentId: string
      blockId: string
      sourceRevisionId: string | null
    }
  | {
      kind: 'search'
      query: string
      searchMode: 'exact' | 'text' | 'semantic'
      spaceIds: string[]
      authorityKinds: KnowledgeAuthority[]
      tags: string[]
    }
  | {
      kind: 'graph'
      rootDocumentId: string | null
      spaceIds: string[]
      relationKinds: string[]
      viewport: GraphViewport
    }
  | { kind: 'workspace'; workspaceId: string }

export interface KnowledgeBookmark {
  schemaVersion: 1
  id: string
  targetKind: KnowledgeTargetKind
  target: KnowledgeTarget
  displayLabel: string
  authorityKind: KnowledgeAuthority | null
  spaceId: string | null
  folderId: string | null
  tags: string[]
  position: number
  revision: number
  createdAt: string
  updatedAt: string
  targetState?: KnowledgeTargetState
  targetDocument?: KnowledgeOpenDescriptor | null
}

export interface KnowledgeBookmarkFolder {
  schemaVersion: 1
  id: string
  name: string
  nameKey: string
  parentFolderId: string | null
  position: number
  revision: number
  createdAt: string
  updatedAt: string
  children: KnowledgeBookmarkFolder[]
}

export interface NavigationReceipt {
  schemaVersion: 1
  operationId: string
  operationKind: string
  entityKind: string
  entityId: string | null
  payloadHash: string
  resultStatus: 'succeeded' | 'conflict'
  resultRevision: number | null
  resultCode: string
  createdAt: string
  completedAt: string
}

export interface BookmarkFilters {
  cursor?: string
  limit?: number
  folderId?: string
  tags?: string[]
  targetKinds?: KnowledgeTargetKind[]
  spaceIds?: string[]
  authorityKinds?: KnowledgeAuthority[]
}

export interface CreateBookmarkCommand {
  operationId: string
  target: KnowledgeTarget
  displayLabel: string
  authorityKind: KnowledgeAuthority | null
  spaceId: string | null
  folderId: string | null
  tags: string[]
  position: number
}

export interface UpdateBookmarkCommand {
  operationId: string
  expectedRevision: number
  target?: KnowledgeTarget
  displayLabel?: string
  authorityKind?: KnowledgeAuthority | null
  spaceId?: string | null
  folderId?: string | null
  tags?: string[]
  position?: number
}

export interface RevisionCommand {
  operationId: string
  expectedRevision: number
}

export interface CreateFolderCommand {
  operationId: string
  name: string
  parentFolderId: string | null
  position: number
  nameKey?: string
}

export interface UpdateFolderCommand extends RevisionCommand {
  name?: string
  parentFolderId?: string | null
  position?: number
  nameKey?: string
}

export interface DeleteFolderCommand extends RevisionCommand {
  childDisposition?: 'move_children' | 'delete_tree'
}

export interface NamedWorkspaceTab {
  id: string
  target: KnowledgeTarget
  displayLabel: string
  viewMode: KnowledgeViewMode
}

export interface NamedWorkspacePane {
  id: string
  activeTabId: string | null
  tabs: NamedWorkspaceTab[]
}

export interface NamedWorkspaceSnapshot {
  version: 1
  activePaneId: string
  nextId: number
  panes: { [paneId: string]: NamedWorkspacePane }
  layout: KnowledgeLayoutNode
  navigation: KnowledgeWorkspaceNavigation
}

export interface NamedKnowledgeWorkspace {
  schemaVersion: 1
  id: string
  name: string
  nameKey: string
  snapshotVersion: 1
  snapshot: NamedWorkspaceSnapshot
  capacitySlot: number
  revision: number
  createdAt: string
  updatedAt: string
}

export interface NamedKnowledgeWorkspaceSummary {
  id: string
  name: string
  revision: number
  updatedAt: string
}

export interface CreateWorkspaceCommand {
  operationId: string
  name: string
  snapshot: NamedWorkspaceSnapshot
  nameKey?: string
}

export interface UpdateWorkspaceCommand extends RevisionCommand {
  name?: string
  snapshot?: NamedWorkspaceSnapshot
  nameKey?: string
}

export interface DuplicateWorkspaceCommand {
  operationId: string
  name: string
  nameKey?: string
}

export interface HydratedWorkspaceTab extends NamedWorkspaceTab {
  targetState: KnowledgeTargetState
  targetDocument: KnowledgeOpenDescriptor | null
}

export interface WorkspaceRestorePane {
  id: string
  activeTabId: string | null
  tabs: HydratedWorkspaceTab[]
}

export interface WorkspaceRestorePlan {
  workspaceId: string
  revision: number
  activePaneId: string
  nextId: number
  panes: { [paneId: string]: WorkspaceRestorePane }
  layout: KnowledgeLayoutNode
  navigation: KnowledgeWorkspaceNavigation
  summary: { [state in KnowledgeTargetState]: number }
}

export interface RandomNoteFilters {
  spaceIds?: string[]
  authorityKinds?: KnowledgeAuthority[]
  tags?: string[]
}

export type RandomNoteResult =
  | { state: 'selected'; document: KnowledgeOpenDescriptor }
  | { state: 'empty'; document: null }

const wireTargetSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('document'), document_id: documentId }).strict(),
  z.object({
    kind: z.literal('block'), document_id: documentId, block_id: blockId,
    source_revision_id: revisionId.nullable().default(null),
  }).strict(),
  z.object({
    kind: z.literal('search'), query: z.string().min(1).max(512),
    search_mode: z.enum(['exact', 'text', 'semantic']).default('text'),
    space_ids: z.array(spaceId).max(32).default([]),
    authority_kinds: z.array(authoritySchema).max(2).default([]),
    tags: z.array(z.string().min(1).max(128)).max(32).default([]),
  }).strict(),
  z.object({
    kind: z.literal('graph'), root_document_id: documentId.nullable().default(null),
    space_ids: z.array(spaceId).max(32).default([]),
    relation_kinds: z.array(z.string().min(1).max(64)).max(32).default([]),
    viewport: graphViewportSchema.default({ x: 0, y: 0, zoom: 1 }),
  }).strict(),
  z.object({ kind: z.literal('workspace'), workspace_id: publicWorkspaceId }).strict(),
])

const camelTargetSchema: z.ZodType<KnowledgeTarget> = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('document'), documentId }).strict(),
  z.object({
    kind: z.literal('block'), documentId, blockId,
    sourceRevisionId: revisionId.nullable(),
  }).strict(),
  z.object({
    kind: z.literal('search'), query: z.string().min(1).max(512),
    searchMode: z.enum(['exact', 'text', 'semantic']),
    spaceIds: z.array(spaceId).max(32), authorityKinds: z.array(authoritySchema).max(2),
    tags: z.array(z.string().min(1).max(128)).max(32),
  }).strict(),
  z.object({
    kind: z.literal('graph'), rootDocumentId: documentId.nullable(),
    spaceIds: z.array(spaceId).max(32),
    relationKinds: z.array(z.string().min(1).max(64)).max(32),
    viewport: graphViewportSchema,
  }).strict(),
  z.object({ kind: z.literal('workspace'), workspaceId: publicWorkspaceId }).strict(),
])

const canonicalRelativeLocatorSchema = z.string().min(1).max(4096)
  .superRefine((value, context) => {
    if (
      /^(?:[\\/]|[A-Za-z]:[\\/])/.test(value)
      || value.includes('\\')
      || value.includes('\0')
      || value.split('/').some((part) => !part || part === '.' || part === '..')
    ) {
      context.addIssue({ code: 'custom', message: 'relative locator must be canonical and relative' })
    }
  })
const descriptorWireSchema = z.object({
  document_id: documentId,
  space_id: spaceId,
  authority_kind: authoritySchema,
  source_kind: z.enum(['overlay', 'obsidian', 'logseq', 'markdown']),
  title: z.string().min(1).max(4096),
  relative_locator: canonicalRelativeLocatorSchema,
  legacy_note_id: z.string().min(1).max(128),
  legacy_container_id: z.string().min(1).max(128),
}).strict()
const bookmarkBaseWireSchema = z.object({
  schema_version: z.literal(1), id: bookmarkId, target_kind: targetKindSchema,
  target: wireTargetSchema, display_label: z.string().min(1).max(512),
  authority_kind: authoritySchema.nullable(), space_id: spaceId.nullable(),
  folder_id: folderId.nullable(), tags: z.array(z.string().min(1).max(128)).max(32),
  position: z.number().int().nonnegative(), revision: z.number().int().min(1),
  created_at: dateTimeSchema, updated_at: dateTimeSchema,
}).strict().superRefine((value, context) => {
  if (value.target_kind !== value.target.kind) {
    context.addIssue({ code: 'custom', message: 'target_kind must match target.kind' })
  }
})
const bookmarkMutationWireSchema = bookmarkBaseWireSchema
const bookmarkWireSchema = bookmarkBaseWireSchema.extend({
  target_state: targetStateSchema,
  target_document: descriptorWireSchema.nullable(),
}).strict()
interface BookmarkFolderWire {
  schema_version: 1
  id: string
  name: string
  name_key: string
  parent_folder_id: string | null
  position: number
  revision: number
  created_at: string
  updated_at: string
  children: BookmarkFolderWire[]
}
const folderWireSchema: z.ZodType<BookmarkFolderWire> = z.lazy(() => z.object({
  schema_version: z.literal(1), id: folderId, name: z.string().min(1).max(256),
  name_key: z.string().min(1).max(256), parent_folder_id: folderId.nullable(),
  position: z.number().int().nonnegative(), revision: z.number().int().min(1),
  created_at: dateTimeSchema, updated_at: dateTimeSchema,
  children: z.array(folderWireSchema).max(256).default([]),
}).strict())
const receiptWireSchema = z.object({
  schema_version: z.literal(1), operation_id: operationId,
  operation_kind: z.string().min(1).max(128), entity_kind: z.string().min(1).max(128),
  entity_id: z.string().min(1).max(128).nullable(),
  payload_hash: z.string().regex(/^[0-9a-f]{64}$/),
  result_status: z.enum(['succeeded', 'conflict']),
  result_revision: z.number().int().min(1).nullable(), result_code: z.string().min(1).max(128),
  created_at: dateTimeSchema, completed_at: dateTimeSchema,
}).strict()

const namedTabWireSchema = z.object({
  id: navigationId, target: wireTargetSchema,
  display_label: z.string().min(1).max(512),
  view_mode: knowledgeViewModeSchema.default('reading'),
}).strict()
const namedPaneWireSchema = z.object({
  id: navigationId, active_tab_id: navigationId.nullable(),
  tabs: z.array(namedTabWireSchema).max(128),
}).strict()
const snapshotWireSchema = z.object({
  version: z.literal(1), active_pane_id: navigationId,
  next_id: z.number().int().min(1), panes: z.record(navigationId, namedPaneWireSchema),
  layout: knowledgeLayoutWireSchema,
  navigation: knowledgeWorkspaceNavigationWireSchema,
}).strict()
const workspaceWireSchema = z.object({
  schema_version: z.literal(1), id: publicWorkspaceId,
  name: z.string().min(1).max(256), name_key: z.string().min(1).max(256),
  snapshot_version: z.literal(1), snapshot: snapshotWireSchema,
  capacity_slot: z.number().int().min(0).max(255), revision: z.number().int().min(1),
  created_at: dateTimeSchema, updated_at: dateTimeSchema,
}).strict()
const workspaceSummaryWireSchema = z.object({
  id: publicWorkspaceId, name: z.string().min(1).max(256),
  revision: z.number().int().min(1), updated_at: dateTimeSchema,
}).strict()
const hydratedTabWireSchema = namedTabWireSchema.extend({
  target_state: targetStateSchema,
  target_document: descriptorWireSchema.nullable(),
}).strict()
const restorePaneWireSchema = z.object({
  id: navigationId, active_tab_id: navigationId.nullable(),
  tabs: z.array(hydratedTabWireSchema).max(128),
}).strict()
const restorePlanWireSchema = z.object({
  workspace_id: publicWorkspaceId, revision: z.number().int().min(1),
  active_pane_id: navigationId, next_id: z.number().int().min(1),
  panes: z.record(navigationId, restorePaneWireSchema),
  layout: knowledgeLayoutWireSchema,
  navigation: knowledgeWorkspaceNavigationWireSchema,
  summary: z.object({
    available: z.number().int().nonnegative(), stale: z.number().int().nonnegative(),
    unavailable: z.number().int().nonnegative(), missing: z.number().int().nonnegative(),
  }).strict(),
}).strict()
const randomNoteWireSchema = z.discriminatedUnion('state', [
  z.object({ state: z.literal('selected'), document: descriptorWireSchema }).strict(),
  z.object({ state: z.literal('empty'), document: z.null() }).strict(),
])

const bookmarkFiltersSchema = z.object({
  cursor: z.string().min(1).max(512).regex(/^[A-Za-z0-9_-]+$/).optional(),
  limit: z.number().int().min(1).max(100).optional(), folderId: folderId.optional(),
  tags: z.array(z.string().min(1).max(128)).max(32).optional(),
  targetKinds: z.array(targetKindSchema).max(5).optional(),
  spaceIds: z.array(spaceId).max(32).optional(),
  authorityKinds: z.array(authoritySchema).max(2).optional(),
}).strict()
const createBookmarkSchema: z.ZodType<CreateBookmarkCommand> = z.object({
  operationId, target: camelTargetSchema, displayLabel: z.string().min(1).max(512),
  authorityKind: authoritySchema.nullable(), spaceId: spaceId.nullable(),
  folderId: folderId.nullable(), tags: z.array(z.string().min(1).max(128)).max(32),
  position: z.number().int().nonnegative(),
}).strict()
const updateBookmarkSchema: z.ZodType<UpdateBookmarkCommand> = z.object({
  operationId, expectedRevision: z.number().int().min(1), target: camelTargetSchema.optional(),
  displayLabel: z.string().min(1).max(512).optional(),
  authorityKind: authoritySchema.nullable().optional(), spaceId: spaceId.nullable().optional(),
  folderId: folderId.nullable().optional(),
  tags: z.array(z.string().min(1).max(128)).max(32).optional(),
  position: z.number().int().nonnegative().optional(),
}).strict()
const revisionCommandSchema: z.ZodType<RevisionCommand> = z.object({
  operationId, expectedRevision: z.number().int().min(1),
}).strict()
const createFolderSchema: z.ZodType<CreateFolderCommand> = z.object({
  operationId, name: z.string().min(1).max(256), parentFolderId: folderId.nullable(),
  position: z.number().int().nonnegative(), nameKey: z.string().min(1).max(256).optional(),
}).strict()
const updateFolderSchema: z.ZodType<UpdateFolderCommand> = z.object({
  operationId, expectedRevision: z.number().int().min(1),
  name: z.string().min(1).max(256).optional(), parentFolderId: folderId.nullable().optional(),
  position: z.number().int().nonnegative().optional(),
  nameKey: z.string().min(1).max(256).optional(),
}).strict()
const deleteFolderSchema: z.ZodType<DeleteFolderCommand> = z.object({
  operationId, expectedRevision: z.number().int().min(1),
  childDisposition: z.enum(['move_children', 'delete_tree']).optional(),
}).strict()
const namedTabSchema: z.ZodType<NamedWorkspaceTab> = z.object({
  id: navigationId, target: camelTargetSchema, displayLabel: z.string().min(1).max(512),
  viewMode: knowledgeViewModeSchema,
}).strict()
const namedPaneSchema: z.ZodType<NamedWorkspacePane> = z.object({
  id: navigationId, activeTabId: navigationId.nullable(), tabs: z.array(namedTabSchema).max(128),
}).strict()
const snapshotSchema: z.ZodType<NamedWorkspaceSnapshot> = z.object({
  version: z.literal(1), activePaneId: navigationId, nextId: z.number().int().min(1),
  panes: z.record(navigationId, namedPaneSchema),
  layout: z.custom<KnowledgeLayoutNode>(), navigation: z.custom<KnowledgeWorkspaceNavigation>(),
}).strict()
const createWorkspaceSchema: z.ZodType<CreateWorkspaceCommand> = z.object({
  operationId, name: z.string().min(1).max(256), snapshot: snapshotSchema,
  nameKey: z.string().min(1).max(256).optional(),
}).strict()
const updateWorkspaceSchema: z.ZodType<UpdateWorkspaceCommand> = z.object({
  operationId, expectedRevision: z.number().int().min(1), name: z.string().min(1).max(256).optional(),
  snapshot: snapshotSchema.optional(), nameKey: z.string().min(1).max(256).optional(),
}).strict().superRefine((value, context) => {
  if (value.name !== undefined && value.snapshot !== undefined) {
    context.addIssue({ code: 'custom', message: 'name and snapshot updates are separate operations' })
  }
})
const duplicateWorkspaceSchema: z.ZodType<DuplicateWorkspaceCommand> = z.object({
  operationId, name: z.string().min(1).max(256), nameKey: z.string().min(1).max(256).optional(),
}).strict()
const randomNoteFiltersSchema: z.ZodType<RandomNoteFilters> = z.object({
  spaceIds: z.array(spaceId).max(32).optional(),
  authorityKinds: z.array(authoritySchema).max(2).optional(),
  tags: z.array(z.string().min(1).max(128)).max(32).optional(),
}).strict()

function assertNoAbsolutePath(value: JsonValue): void {
  const stack: JsonValue[] = [value]
  const seen = new WeakSet<object>()
  while (stack.length > 0) {
    const current = stack.pop()
    if (typeof current === 'string') {
      if (/^(?:[\\/]|[A-Za-z]:[\\/])/.test(current)) {
        throw new Error('Knowledge navigation contained an absolute path')
      }
      continue
    }
    if (current === undefined || current === null || typeof current !== 'object') continue
    if (seen.has(current)) continue
    seen.add(current)
    stack.push(...(Array.isArray(current) ? current : Object.values(current)))
  }
}

function parseWire<T>(schema: z.ZodType<T>, value: JsonValue): T {
  assertNoAbsolutePath(value)
  return schema.parse(value)
}

function preflightFolderForest(value: JsonValue): void {
  if (!Array.isArray(value)) throw new Error('bookmark folder tree has an invalid shape')
  const stack = value.map((node) => ({ node, depth: 1 }))
  const seen = new WeakSet<object>()
  let count = 0
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    count += 1
    if (count > 256 || current.depth > 16) {
      throw new Error('bookmark folder tree exceeds bounds')
    }
    if (!current.node || typeof current.node !== 'object' || Array.isArray(current.node)) {
      throw new Error('bookmark folder tree has an invalid shape')
    }
    if (seen.has(current.node)) throw new Error('bookmark folder tree contains a cycle')
    seen.add(current.node)
    const children = current.node.children
    if (children === undefined) continue
    if (!Array.isArray(children)) throw new Error('bookmark folder children must be an array')
    for (const child of children) stack.push({ node: child, depth: current.depth + 1 })
  }
}

function preflightLayout(
  layout: JsonValue,
  paneIds: Set<string>,
  casing: 'wire' | 'camel',
): void {
  const stack = [{ node: layout, depth: 1 }]
  const seen = new WeakSet<object>()
  const splitIds = new Set<string>()
  const coveredPanes: string[] = []
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (current.depth > 64) throw new Error('workspace layout cannot exceed depth 64')
    if (!current.node || typeof current.node !== 'object' || Array.isArray(current.node)) {
      throw new Error('workspace layout has an invalid shape')
    }
    if (seen.has(current.node)) throw new Error('workspace layout cannot contain cycles')
    seen.add(current.node)
    if (current.node.type === 'pane') {
      const paneIdValue = current.node[casing === 'wire' ? 'pane_id' : 'paneId']
      if (typeof paneIdValue !== 'string') throw new Error('workspace pane ID is invalid')
      coveredPanes.push(paneIdValue)
      continue
    }
    if (current.node.type !== 'split' || typeof current.node.id !== 'string') {
      throw new Error('workspace layout has an invalid shape')
    }
    if (splitIds.has(current.node.id)) throw new Error('split IDs must be unique')
    splitIds.add(current.node.id)
    stack.push(
      { node: current.node.first ?? null, depth: current.depth + 1 },
      { node: current.node.second ?? null, depth: current.depth + 1 },
    )
  }
  if (new Set(coveredPanes).size !== coveredPanes.length) {
    throw new Error('workspace layout cannot duplicate panes')
  }
  if (
    coveredPanes.length !== paneIds.size
    || coveredPanes.some((paneIdValue) => !paneIds.has(paneIdValue))
  ) {
    throw new Error('workspace layout must reference every pane exactly once')
  }
}

function preflightWorkspaceState(
  value: JsonValue,
  casing: 'wire' | 'camel',
  hydrated: boolean,
  expectedSummary?: { [state in KnowledgeTargetState]: number },
): void {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('workspace snapshot has an invalid shape')
  }
  const panesKey = 'panes'
  const activePaneKey = casing === 'wire' ? 'active_pane_id' : 'activePaneId'
  const activeTabKey = casing === 'wire' ? 'active_tab_id' : 'activeTabId'
  const targetStateKey = casing === 'wire' ? 'target_state' : 'targetState'
  const panesValue = value[panesKey]
  if (!panesValue || typeof panesValue !== 'object' || Array.isArray(panesValue)) {
    throw new Error('workspace panes have an invalid shape')
  }
  const panes = Object.entries(panesValue)
  if (panes.length > 32) throw new Error('workspace cannot contain more than 32 panes')
  const paneIds = new Set(panes.map(([paneKey]) => paneKey))
  if (typeof value[activePaneKey] !== 'string' || !paneIds.has(value[activePaneKey])) {
    throw new Error('active pane must exist in the workspace')
  }
  const stateCounts = { available: 0, stale: 0, unavailable: 0, missing: 0 }
  let totalTabs = 0
  for (const [paneKey, paneValue] of panes) {
    if (!paneValue || typeof paneValue !== 'object' || Array.isArray(paneValue)) {
      throw new Error('workspace pane has an invalid shape')
    }
    if (paneValue.id !== paneKey) throw new Error('pane dictionary keys must match pane IDs')
    const tabs = paneValue.tabs
    if (!Array.isArray(tabs)) throw new Error('workspace tabs must be an array')
    totalTabs += tabs.length
    if (totalTabs > 128) throw new Error('workspace cannot contain more than 128 tabs')
    const tabIds = new Set<string>()
    for (const tab of tabs) {
      if (!tab || typeof tab !== 'object' || Array.isArray(tab) || typeof tab.id !== 'string') {
        throw new Error('workspace tab has an invalid shape')
      }
      if (tabIds.has(tab.id)) throw new Error('tab IDs must be unique within each pane')
      tabIds.add(tab.id)
      if (hydrated) {
        const state = tab[targetStateKey]
        if (state === 'available' || state === 'stale' || state === 'unavailable' || state === 'missing') {
          stateCounts[state] += 1
        }
      }
    }
    const activeTabId = paneValue[activeTabKey]
    if (activeTabId !== null && (typeof activeTabId !== 'string' || !tabIds.has(activeTabId))) {
      throw new Error('active tab must exist in its pane')
    }
  }
  preflightLayout(value.layout ?? null, paneIds, casing)
  if (expectedSummary) {
    const summaryTotal = Object.values(expectedSummary).reduce((total, count) => total + count, 0)
    if (summaryTotal !== totalTabs) throw new Error('restore summary total must match restored tabs')
    for (const state of ['available', 'stale', 'unavailable', 'missing'] as const) {
      if (expectedSummary[state] !== stateCounts[state]) {
        throw new Error('restore summary must match restored target states')
      }
    }
  }
}

function targetFromWire(target: z.infer<typeof wireTargetSchema>): KnowledgeTarget {
  if (target.kind === 'document') return { kind: 'document', documentId: target.document_id }
  if (target.kind === 'block') {
    return {
      kind: 'block', documentId: target.document_id, blockId: target.block_id,
      sourceRevisionId: target.source_revision_id,
    }
  }
  if (target.kind === 'search') {
    return {
      kind: 'search', query: target.query, searchMode: target.search_mode,
      spaceIds: target.space_ids, authorityKinds: target.authority_kinds, tags: target.tags,
    }
  }
  if (target.kind === 'graph') {
    return {
      kind: 'graph', rootDocumentId: target.root_document_id,
      spaceIds: target.space_ids, relationKinds: target.relation_kinds,
      viewport: target.viewport,
    }
  }
  return { kind: 'workspace', workspaceId: target.workspace_id }
}

function targetToWire(target: KnowledgeTarget): z.input<typeof wireTargetSchema> {
  const parsed = camelTargetSchema.parse(target)
  if (parsed.kind === 'document') return { kind: 'document', document_id: parsed.documentId }
  if (parsed.kind === 'block') {
    return {
      kind: 'block', document_id: parsed.documentId, block_id: parsed.blockId,
      source_revision_id: parsed.sourceRevisionId,
    }
  }
  if (parsed.kind === 'search') {
    return {
      kind: 'search', query: parsed.query, search_mode: parsed.searchMode,
      space_ids: parsed.spaceIds, authority_kinds: parsed.authorityKinds, tags: parsed.tags,
    }
  }
  if (parsed.kind === 'graph') {
    return {
      kind: 'graph', root_document_id: parsed.rootDocumentId,
      space_ids: parsed.spaceIds, relation_kinds: parsed.relationKinds,
      viewport: parsed.viewport,
    }
  }
  return { kind: 'workspace', workspace_id: parsed.workspaceId }
}

function descriptorFromWire(value: z.infer<typeof descriptorWireSchema>): KnowledgeOpenDescriptor {
  return {
    documentId: value.document_id, spaceId: value.space_id,
    authorityKind: value.authority_kind, sourceKind: value.source_kind,
    title: value.title, relativeLocator: value.relative_locator,
    legacyNoteId: value.legacy_note_id, legacyContainerId: value.legacy_container_id,
  }
}

function bookmarkFromWire(
  value: z.infer<typeof bookmarkMutationWireSchema> | z.infer<typeof bookmarkWireSchema>,
): KnowledgeBookmark {
  const base: KnowledgeBookmark = {
    schemaVersion: value.schema_version, id: value.id, targetKind: value.target_kind,
    target: targetFromWire(value.target), displayLabel: value.display_label,
    authorityKind: value.authority_kind, spaceId: value.space_id, folderId: value.folder_id,
    tags: value.tags, position: value.position, revision: value.revision,
    createdAt: value.created_at, updatedAt: value.updated_at,
  }
  if ('target_state' in value) {
    return {
      ...base, targetState: value.target_state,
      targetDocument: value.target_document ? descriptorFromWire(value.target_document) : null,
    }
  }
  return base
}

function folderFromWire(value: BookmarkFolderWire): KnowledgeBookmarkFolder {
  return {
    schemaVersion: value.schema_version, id: value.id, name: value.name,
    nameKey: value.name_key, parentFolderId: value.parent_folder_id,
    position: value.position, revision: value.revision,
    createdAt: value.created_at, updatedAt: value.updated_at,
    children: value.children.map(folderFromWire),
  }
}

function receiptFromWire(value: z.infer<typeof receiptWireSchema>): NavigationReceipt {
  return {
    schemaVersion: value.schema_version, operationId: value.operation_id,
    operationKind: value.operation_kind, entityKind: value.entity_kind,
    entityId: value.entity_id, payloadHash: value.payload_hash,
    resultStatus: value.result_status, resultRevision: value.result_revision,
    resultCode: value.result_code, createdAt: value.created_at, completedAt: value.completed_at,
  }
}

function navigationFromWire(
  value: z.infer<typeof knowledgeWorkspaceNavigationWireSchema>,
): KnowledgeWorkspaceNavigation {
  return {
    utilityMode: value.utility_mode, sidebarVisible: value.sidebar_visible,
    sidebarWidth: value.sidebar_width, activeBookmarkFolderId: value.active_bookmark_folder_id,
    bookmarkTags: value.bookmark_tags, sourceTreeQuery: value.source_tree_query,
    searchQuery: value.search_query, searchMode: value.search_mode, activeDraftId: value.active_draft_id,
    selectedSpaceIds: value.selected_space_ids, authorityFilters: value.authority_filters,
    metricsVisible: value.metrics_visible,
  }
}

function navigationToWire(value: KnowledgeWorkspaceNavigation) {
  return knowledgeWorkspaceNavigationWireSchema.parse({
    utility_mode: value.utilityMode, sidebar_visible: value.sidebarVisible,
    sidebar_width: value.sidebarWidth,
    active_bookmark_folder_id: value.activeBookmarkFolderId,
    bookmark_tags: value.bookmarkTags, source_tree_query: value.sourceTreeQuery,
    search_query: value.searchQuery, search_mode: value.searchMode, active_draft_id: value.activeDraftId,
    selected_space_ids: value.selectedSpaceIds, authority_filters: value.authorityFilters,
    metrics_visible: value.metricsVisible,
  })
}

function layoutFromWire(value: z.infer<typeof knowledgeLayoutWireSchema>): KnowledgeLayoutNode {
  if (value.type === 'pane') return { type: 'pane', paneId: value.pane_id }
  return {
    type: 'split', id: value.id, direction: value.direction, firstSize: value.first_size,
    first: layoutFromWire(value.first), second: layoutFromWire(value.second),
  }
}

function layoutToWire(value: KnowledgeLayoutNode): z.input<typeof knowledgeLayoutWireSchema> {
  if (value.type === 'pane') return { type: 'pane', pane_id: value.paneId }
  return {
    type: 'split', id: value.id, direction: value.direction,
    first_size: value.firstSize,
    first: layoutToWire(value.first), second: layoutToWire(value.second),
  }
}

function snapshotFromWire(value: z.infer<typeof snapshotWireSchema>): NamedWorkspaceSnapshot {
  return {
    version: value.version, activePaneId: value.active_pane_id, nextId: value.next_id,
    panes: Object.fromEntries(Object.entries(value.panes).map(([paneIdValue, pane]) => [
      paneIdValue,
      {
        id: pane.id, activeTabId: pane.active_tab_id,
        tabs: pane.tabs.map((tab) => ({
          id: tab.id, target: targetFromWire(tab.target),
          displayLabel: tab.display_label, viewMode: tab.view_mode,
        })),
      },
    ])),
    layout: layoutFromWire(value.layout),
    navigation: navigationFromWire(value.navigation),
  }
}

function snapshotToWire(value: NamedWorkspaceSnapshot): z.infer<typeof snapshotWireSchema> {
  const parsed = snapshotSchema.parse(value)
  preflightWorkspaceState(parsed as never, 'camel', false)
  const wire = {
    version: parsed.version, active_pane_id: parsed.activePaneId, next_id: parsed.nextId,
    panes: Object.fromEntries(Object.entries(parsed.panes).map(([paneIdValue, pane]) => [
      paneIdValue,
      {
        id: pane.id, active_tab_id: pane.activeTabId,
        tabs: pane.tabs.map((tab) => ({
          id: tab.id, target: targetToWire(tab.target),
          display_label: tab.displayLabel, view_mode: tab.viewMode,
        })),
      },
    ])),
    layout: layoutToWire(parsed.layout), navigation: navigationToWire(parsed.navigation),
  }
  return snapshotWireSchema.parse(wire)
}

function workspaceFromWire(value: z.infer<typeof workspaceWireSchema>): NamedKnowledgeWorkspace {
  return {
    schemaVersion: value.schema_version, id: value.id, name: value.name,
    nameKey: value.name_key, snapshotVersion: value.snapshot_version,
    snapshot: snapshotFromWire(value.snapshot), capacitySlot: value.capacity_slot,
    revision: value.revision, createdAt: value.created_at, updatedAt: value.updated_at,
  }
}

function parseWorkspace(value: JsonValue): NamedKnowledgeWorkspace {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('workspace response has an invalid shape')
  }
  preflightWorkspaceState(value.snapshot ?? null, 'wire', false)
  return workspaceFromWire(parseWire(workspaceWireSchema, value))
}

function restorePlanFromWire(value: z.infer<typeof restorePlanWireSchema>): WorkspaceRestorePlan {
  return {
    workspaceId: value.workspace_id, revision: value.revision,
    activePaneId: value.active_pane_id, nextId: value.next_id,
    panes: Object.fromEntries(Object.entries(value.panes).map(([paneIdValue, pane]) => [
      paneIdValue,
      {
        id: pane.id, activeTabId: pane.active_tab_id,
        tabs: pane.tabs.map((tab) => ({
          id: tab.id, target: targetFromWire(tab.target), displayLabel: tab.display_label,
          viewMode: tab.view_mode, targetState: tab.target_state,
          targetDocument: tab.target_document ? descriptorFromWire(tab.target_document) : null,
        })),
      },
    ])),
    layout: layoutFromWire(value.layout), navigation: navigationFromWire(value.navigation),
    summary: { ...value.summary },
  }
}

function deepFreeze<T extends object>(value: T): Readonly<T> {
  const stack: object[] = [value]
  const seen = new WeakSet<object>()
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current || seen.has(current)) continue
    seen.add(current)
    for (const child of Object.values(current)) {
      if (child && typeof child === 'object') stack.push(child)
    }
    Object.freeze(current)
  }
  return value
}

export function createKnowledgeNavigationOperationId(): string {
  return crypto.randomUUID()
}

/** Prepare exactly once at the UI event boundary; reuse the returned object for retries. */
export function prepareKnowledgeNavigationCommand<T extends object>(
  command: T,
): Readonly<T & { operationId: string }> {
  const existing = 'operationId' in command ? command.operationId : undefined
  if (typeof existing === 'string' && existing && Object.isFrozen(command)) {
    return command as Readonly<T & { operationId: string }>
  }
  const prepared = {
    ...structuredClone(command),
    operationId: typeof existing === 'string' && existing
      ? existing
      : createKnowledgeNavigationOperationId(),
  }
  return deepFreeze(prepared)
}

export function parseBookmark(value: JsonValue): KnowledgeBookmark {
  return bookmarkFromWire(parseWire(bookmarkWireSchema, value))
}

export function parseBookmarkFolder(value: JsonValue): KnowledgeBookmarkFolder {
  preflightFolderForest([value])
  return folderFromWire(parseWire(folderWireSchema, value))
}

function bookmarkCreateToWire(command: CreateBookmarkCommand) {
  const value = createBookmarkSchema.parse(command)
  return {
    operation_id: value.operationId, target: targetToWire(value.target),
    display_label: value.displayLabel, authority_kind: value.authorityKind,
    space_id: value.spaceId, folder_id: value.folderId, tags: value.tags,
    position: value.position,
  }
}

function bookmarkUpdateToWire(command: UpdateBookmarkCommand) {
  const value = updateBookmarkSchema.parse(command)
  return {
    operation_id: value.operationId, expected_revision: value.expectedRevision,
    ...(value.target !== undefined ? { target: targetToWire(value.target) } : {}),
    ...(value.displayLabel !== undefined ? { display_label: value.displayLabel } : {}),
    ...(value.authorityKind !== undefined ? { authority_kind: value.authorityKind } : {}),
    ...(value.spaceId !== undefined ? { space_id: value.spaceId } : {}),
    ...(value.folderId !== undefined ? { folder_id: value.folderId } : {}),
    ...(value.tags !== undefined ? { tags: value.tags } : {}),
    ...(value.position !== undefined ? { position: value.position } : {}),
  }
}

function revisionToWire(command: RevisionCommand) {
  const value = revisionCommandSchema.parse(command)
  return { operation_id: value.operationId, expected_revision: value.expectedRevision }
}

function createFolderToWire(command: CreateFolderCommand) {
  const value = createFolderSchema.parse(command)
  return {
    operation_id: value.operationId, name: value.name,
    parent_folder_id: value.parentFolderId, position: value.position,
    ...(value.nameKey !== undefined ? { name_key: value.nameKey } : {}),
  }
}

function updateFolderToWire(command: UpdateFolderCommand) {
  const value = updateFolderSchema.parse(command)
  return {
    operation_id: value.operationId, expected_revision: value.expectedRevision,
    ...(value.name !== undefined ? { name: value.name } : {}),
    ...(value.parentFolderId !== undefined ? { parent_folder_id: value.parentFolderId } : {}),
    ...(value.position !== undefined ? { position: value.position } : {}),
    ...(value.nameKey !== undefined ? { name_key: value.nameKey } : {}),
  }
}

function deleteFolderToWire(command: DeleteFolderCommand) {
  const value = deleteFolderSchema.parse(command)
  return {
    operation_id: value.operationId, expected_revision: value.expectedRevision,
    ...(value.childDisposition !== undefined
      ? { child_disposition: value.childDisposition }
      : {}),
  }
}

function createWorkspaceToWire(command: CreateWorkspaceCommand) {
  const value = createWorkspaceSchema.parse(command)
  return {
    operation_id: value.operationId, name: value.name,
    snapshot: snapshotToWire(value.snapshot),
    ...(value.nameKey !== undefined ? { name_key: value.nameKey } : {}),
  }
}

function updateWorkspaceToWire(command: UpdateWorkspaceCommand) {
  const value = updateWorkspaceSchema.parse(command)
  return {
    operation_id: value.operationId, expected_revision: value.expectedRevision,
    ...(value.name !== undefined ? { name: value.name } : {}),
    ...(value.snapshot !== undefined ? { snapshot: snapshotToWire(value.snapshot) } : {}),
    ...(value.nameKey !== undefined ? { name_key: value.nameKey } : {}),
  }
}

function duplicateWorkspaceToWire(command: DuplicateWorkspaceCommand) {
  const value = duplicateWorkspaceSchema.parse(command)
  return {
    operation_id: value.operationId, name: value.name,
    ...(value.nameKey !== undefined ? { name_key: value.nameKey } : {}),
  }
}

export const knowledgeNavigationApi = {
  listBookmarks: async (filters: BookmarkFilters = {}) => {
    const value = bookmarkFiltersSchema.parse(filters)
    const params = {
      ...(value.cursor !== undefined ? { cursor: value.cursor } : {}),
      ...(value.limit !== undefined ? { limit: value.limit } : {}),
      ...(value.folderId !== undefined ? { folder_id: value.folderId } : {}),
      ...(value.tags !== undefined ? { tag: value.tags } : {}),
      ...(value.targetKinds !== undefined ? { target_kind: value.targetKinds } : {}),
      ...(value.spaceIds !== undefined ? { space_id: value.spaceIds } : {}),
      ...(value.authorityKinds !== undefined ? { authority_kind: value.authorityKinds } : {}),
    }
    const response = await apiClient.get(`${navigationPath}/bookmarks`, { params })
    const wire = parseWire(z.object({
      items: z.array(bookmarkWireSchema).max(100),
      next_cursor: z.string().max(512).regex(/^[A-Za-z0-9_-]+$/).nullable(),
    }).strict(), response.data as JsonValue)
    return { items: wire.items.map(bookmarkFromWire), nextCursor: wire.next_cursor }
  },

  createBookmark: async (command: CreateBookmarkCommand): Promise<KnowledgeBookmark> => {
    const response = await apiClient.post(`${navigationPath}/bookmarks`, bookmarkCreateToWire(command))
    return bookmarkFromWire(parseWire(bookmarkMutationWireSchema, response.data as JsonValue))
  },

  updateBookmark: async (
    idValue: string,
    command: UpdateBookmarkCommand,
  ): Promise<KnowledgeBookmark> => {
    const response = await apiClient.patch(
      `${navigationPath}/bookmarks/${encodeURIComponent(bookmarkId.parse(idValue))}`,
      bookmarkUpdateToWire(command),
    )
    return bookmarkFromWire(parseWire(bookmarkMutationWireSchema, response.data as JsonValue))
  },

  deleteBookmark: async (
    idValue: string,
    command: RevisionCommand,
  ): Promise<NavigationReceipt> => {
    const response = await apiClient.delete(
      `${navigationPath}/bookmarks/${encodeURIComponent(bookmarkId.parse(idValue))}`,
      { data: revisionToWire(command) },
    )
    return receiptFromWire(parseWire(receiptWireSchema, response.data as JsonValue))
  },

  listFolders: async (): Promise<{ items: KnowledgeBookmarkFolder[] }> => {
    const response = await apiClient.get(`${navigationPath}/bookmark-folders`)
    const responseValue = response.data as JsonValue
    if (!responseValue || typeof responseValue !== 'object' || Array.isArray(responseValue)) {
      throw new Error('bookmark folder response has an invalid shape')
    }
    preflightFolderForest(responseValue.items ?? null)
    const wire = parseWire(z.object({ items: z.array(folderWireSchema).max(256) }).strict(), responseValue)
    return { items: wire.items.map(folderFromWire) }
  },

  createFolder: async (command: CreateFolderCommand): Promise<KnowledgeBookmarkFolder> => {
    const response = await apiClient.post(`${navigationPath}/bookmark-folders`, createFolderToWire(command))
    return parseBookmarkFolder(response.data as JsonValue)
  },

  updateFolder: async (
    idValue: string,
    command: UpdateFolderCommand,
  ): Promise<KnowledgeBookmarkFolder> => {
    const response = await apiClient.patch(
      `${navigationPath}/bookmark-folders/${encodeURIComponent(folderId.parse(idValue))}`,
      updateFolderToWire(command),
    )
    return parseBookmarkFolder(response.data as JsonValue)
  },

  deleteFolder: async (
    idValue: string,
    command: DeleteFolderCommand,
  ): Promise<NavigationReceipt> => {
    const response = await apiClient.delete(
      `${navigationPath}/bookmark-folders/${encodeURIComponent(folderId.parse(idValue))}`,
      { data: deleteFolderToWire(command) },
    )
    return receiptFromWire(parseWire(receiptWireSchema, response.data as JsonValue))
  },

  listWorkspaces: async (): Promise<{ items: NamedKnowledgeWorkspaceSummary[] }> => {
    const response = await apiClient.get(`${navigationPath}/workspaces`)
    const wire = parseWire(z.object({ items: z.array(workspaceSummaryWireSchema).max(256) }).strict(), response.data as JsonValue)
    return {
      items: wire.items.map((item) => ({
        id: item.id, name: item.name, revision: item.revision, updatedAt: item.updated_at,
      })),
    }
  },

  createWorkspace: async (command: CreateWorkspaceCommand): Promise<NamedKnowledgeWorkspace> => {
    const response = await apiClient.post(`${navigationPath}/workspaces`, createWorkspaceToWire(command))
    return parseWorkspace(response.data as JsonValue)
  },

  getWorkspace: async (idValue: string): Promise<NamedKnowledgeWorkspace> => {
    const response = await apiClient.get(
      `${navigationPath}/workspaces/${encodeURIComponent(publicWorkspaceId.parse(idValue))}`,
    )
    return parseWorkspace(response.data as JsonValue)
  },

  updateWorkspace: async (
    idValue: string,
    command: UpdateWorkspaceCommand,
  ): Promise<NamedKnowledgeWorkspace> => {
    const response = await apiClient.patch(
      `${navigationPath}/workspaces/${encodeURIComponent(publicWorkspaceId.parse(idValue))}`,
      updateWorkspaceToWire(command),
    )
    return parseWorkspace(response.data as JsonValue)
  },

  duplicateWorkspace: async (
    idValue: string,
    command: DuplicateWorkspaceCommand,
  ): Promise<NamedKnowledgeWorkspace> => {
    const response = await apiClient.post(
      `${navigationPath}/workspaces/${encodeURIComponent(publicWorkspaceId.parse(idValue))}/duplicate`,
      duplicateWorkspaceToWire(command),
    )
    return parseWorkspace(response.data as JsonValue)
  },

  deleteWorkspace: async (
    idValue: string,
    command: RevisionCommand,
  ): Promise<NavigationReceipt> => {
    const response = await apiClient.delete(
      `${navigationPath}/workspaces/${encodeURIComponent(publicWorkspaceId.parse(idValue))}`,
      { data: revisionToWire(command) },
    )
    return receiptFromWire(parseWire(receiptWireSchema, response.data as JsonValue))
  },

  restorePlan: async (idValue: string, revision: number): Promise<WorkspaceRestorePlan> => {
    const parsedRevision = z.number().int().min(1).parse(revision)
    const response = await apiClient.post(
      `${navigationPath}/workspaces/${encodeURIComponent(publicWorkspaceId.parse(idValue))}/restore-plan`,
      { revision: parsedRevision },
    )
    const responseValue = response.data as JsonValue
    if (!responseValue || typeof responseValue !== 'object' || Array.isArray(responseValue)) {
      throw new Error('restore plan has an invalid shape')
    }
    const summary = z.object({
      available: z.number().int().nonnegative(), stale: z.number().int().nonnegative(),
      unavailable: z.number().int().nonnegative(), missing: z.number().int().nonnegative(),
    }).strict().parse(responseValue.summary)
    preflightWorkspaceState(responseValue, 'wire', true, summary)
    return restorePlanFromWire(parseWire(restorePlanWireSchema, responseValue))
  },

  randomNote: async (filters: RandomNoteFilters = {}): Promise<RandomNoteResult> => {
    const value = randomNoteFiltersSchema.parse(filters)
    const response = await apiClient.post(`${navigationPath}/random-note`, {
      ...(value.spaceIds !== undefined ? { space_ids: value.spaceIds } : {}),
      ...(value.authorityKinds !== undefined ? { authority_kinds: value.authorityKinds } : {}),
      ...(value.tags !== undefined ? { tags: value.tags } : {}),
    })
    const wire = parseWire(randomNoteWireSchema, response.data as JsonValue)
    return wire.state === 'selected'
      ? { state: 'selected', document: descriptorFromWire(wire.document) }
      : { state: 'empty', document: null }
  },
}
