import { z } from 'zod'

import apiClient from './client'
import {
  knowledgeLayoutWireSchema,
  knowledgeWorkspaceNavigationWireSchema,
  knowledgeViewModeSchema,
} from './knowledge-workspace'

const navigationPath = '/deeper-notebook/knowledge'
const id = (prefix: string) => z.string().regex(new RegExp(`^${prefix}:[A-Za-z0-9_-]+$`)).max(128)
const localId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/)
const targetState = z.enum(['available', 'stale', 'unavailable', 'missing'])
const authority = z.enum(['app_owned', 'external_read_only'])
const targetKind = z.enum(['document', 'block', 'search', 'graph', 'workspace'])
const viewport = z.object({ x: z.number().finite(), y: z.number().finite(), zoom: z.number().finite().min(0.1).max(10) }).strict()

export const knowledgeTargetSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('document'), document_id: id('knowledge_engine_document') }).strict(),
  z.object({ kind: z.literal('block'), document_id: id('knowledge_engine_document'), block_id: id('knowledge_engine_block'), source_revision_id: id('knowledge_engine_(?:revision|source_revision)').nullable().optional() }).strict(),
  z.object({ kind: z.literal('search'), query: z.string().min(1).max(512), search_mode: z.enum(['exact', 'text', 'semantic']).default('text'), space_ids: z.array(id('knowledge_engine_space')).max(32).default([]), authority_kinds: z.array(authority).max(2).default([]), tags: z.array(z.string().min(1).max(128)).max(32).default([]) }).strict(),
  z.object({ kind: z.literal('graph'), root_document_id: id('knowledge_engine_document').nullable().default(null), space_ids: z.array(id('knowledge_engine_space')).max(32).default([]), relation_kinds: z.array(z.string().min(1).max(64)).max(32).default([]), viewport: viewport.default({ x: 0, y: 0, zoom: 1 }) }).strict(),
  z.object({ kind: z.literal('workspace'), workspace_id: id('named_knowledge_workspace') }).strict(),
])

const canonicalRelativeLocatorSchema = z.string().min(1).max(4096).superRefine((value, context) => {
  if (/^(?:[\\/]|[A-Za-z]:[\\/])/.test(value) || value.includes('\\') || value.includes('\0') || value.split('/').some((part) => !part || part === '.' || part === '..')) {
    context.addIssue({ code: 'custom', message: 'relative locator must be canonical and relative' })
  }
})
const descriptorSchema = z.object({
  document_id: id('knowledge_engine_document'), space_id: id('knowledge_engine_space'), authority_kind: authority,
  source_kind: z.enum(['overlay', 'obsidian', 'logseq', 'markdown']), title: z.string().min(1).max(4096),
  relative_locator: canonicalRelativeLocatorSchema, legacy_note_id: z.string().min(1).max(128), legacy_container_id: z.string().min(1).max(128),
}).strict()
const bookmarkBase = z.object({
  schema_version: z.literal(1), id: id('knowledge_bookmark'), target_kind: targetKind,
  target: knowledgeTargetSchema, display_label: z.string().min(1).max(512), authority_kind: authority.nullable(),
  space_id: id('knowledge_engine_space').nullable(), folder_id: id('knowledge_bookmark_folder').nullable(),
  tags: z.array(z.string().min(1).max(128)).max(32), position: z.number().int().nonnegative(), revision: z.number().int().min(1),
  created_at: z.string(), updated_at: z.string(),
}).strict().superRefine((value, context) => {
  if (value.target_kind !== value.target.kind) context.addIssue({ code: 'custom', message: 'target_kind must match target.kind' })
})
export const bookmarkMutationWireSchema = bookmarkBase
export const bookmarkWireSchema = bookmarkBase.extend({ target_state: targetState, target_document: descriptorSchema.nullable() }).strict()
interface BookmarkFolderWire { schema_version: 1; id: string; name: string; name_key: string; parent_folder_id: string | null; position: number; revision: number; created_at: string; updated_at: string; children?: BookmarkFolderWire[] }
export const bookmarkFolderWireSchema: z.ZodType<BookmarkFolderWire> = z.lazy(() => z.object({ schema_version: z.literal(1), id: id('knowledge_bookmark_folder'), name: z.string().min(1).max(256), name_key: z.string().min(1).max(256), parent_folder_id: id('knowledge_bookmark_folder').nullable(), position: z.number().int().nonnegative(), revision: z.number().int().min(1), created_at: z.string(), updated_at: z.string(), children: z.array(bookmarkFolderWireSchema).max(256).optional() }).strict())
const receiptSchema = z.object({ schema_version: z.literal(1), operation_id: localId, operation_kind: z.string().min(1), entity_kind: z.string().min(1), entity_id: z.string().min(1).max(128).nullable(), payload_hash: z.string().regex(/^[0-9a-f]{64}$/), result_status: z.enum(['succeeded', 'conflict']), result_revision: z.number().int().min(1).nullable(), result_code: z.string().min(1), created_at: z.string(), completed_at: z.string() }).strict()
const workspaceSummarySchema = z.object({ id: id('named_knowledge_workspace'), name: z.string().min(1).max(256), revision: z.number().int().min(1), updated_at: z.string() }).strict()
const namedWorkspaceTabWireSchema = z.object({ id: localId, target: knowledgeTargetSchema, display_label: z.string().min(1).max(512), view_mode: knowledgeViewModeSchema.default('reading') }).strict()
const namedWorkspacePaneWireSchema = z.object({ id: localId, active_tab_id: localId.nullable(), tabs: z.array(namedWorkspaceTabWireSchema).max(128) }).strict()
const namedWorkspaceSnapshotWireSchema = z.object({ version: z.literal(1), active_pane_id: localId, next_id: z.number().int().min(1), panes: z.record(localId, namedWorkspacePaneWireSchema), layout: knowledgeLayoutWireSchema, navigation: knowledgeWorkspaceNavigationWireSchema }).strict()
const workspaceWireSchema = z.object({ schema_version: z.literal(1), id: id('named_knowledge_workspace'), name: z.string().min(1).max(256), name_key: z.string().min(1).max(256), snapshot_version: z.literal(1), snapshot: namedWorkspaceSnapshotWireSchema, capacity_slot: z.number().int().min(0).max(255), revision: z.number().int().min(1), created_at: z.string(), updated_at: z.string() }).strict()
const restoredTabWireSchema = namedWorkspaceTabWireSchema.extend({ target_state: targetState, target_document: descriptorSchema.nullable() }).strict()
const restorePaneWireSchema = z.object({ id: localId, active_tab_id: localId.nullable(), tabs: z.array(restoredTabWireSchema).max(128) }).strict()
const restorePlanWireSchema = z.object({ workspace_id: id('named_knowledge_workspace'), revision: z.number().int().min(1), active_pane_id: localId, next_id: z.number().int().min(1), panes: z.record(localId, restorePaneWireSchema), layout: knowledgeLayoutWireSchema, navigation: knowledgeWorkspaceNavigationWireSchema, summary: z.object({ available: z.number().int().nonnegative(), stale: z.number().int().nonnegative(), unavailable: z.number().int().nonnegative(), missing: z.number().int().nonnegative() }).strict() }).strict()
const randomNoteWireSchema = z.object({ state: z.enum(['selected', 'empty']), document: descriptorSchema.nullable() }).strict().superRefine((value, context) => { if ((value.state === 'selected') !== Boolean(value.document)) context.addIssue({ code: 'custom', message: 'selected state requires a document' }) })

function structuralPathCheck(value: unknown): void {
  const stack = [value]
  const seen = new WeakSet<object>()
  while (stack.length) {
    const current = stack.pop()
    if (typeof current === 'string') {
      if (/^(?:[\\/]|[A-Za-z]:[\\/])/.test(current)) throw new Error('Knowledge navigation contained an absolute path')
      continue
    }
    if (!current || typeof current !== 'object' || seen.has(current)) continue
    seen.add(current)
    if (Array.isArray(current)) stack.push(...current)
    else stack.push(...Object.values(current))
  }
}
function preflightFolderTree(value: unknown): void {
  const stack: Array<{ node: unknown; depth: number }> = [{ node: value, depth: 1 }]
  let count = 0
  while (stack.length) {
    const { node, depth } = stack.pop()!
    count += 1
    if (count > 256 || depth > 16) throw new Error('bookmark folder tree exceeds bounds')
    if (!node || typeof node !== 'object' || Array.isArray(node)) continue
    const children = (node as { children?: unknown }).children
    if (Array.isArray(children)) for (const child of children) stack.push({ node: child, depth: depth + 1 })
  }
}

function parse<T>(schema: z.ZodType<T>, value: unknown): T { structuralPathCheck(value); return schema.parse(value) }
export function createKnowledgeNavigationOperationId(): string { return crypto.randomUUID() }
function targetToWire(target: Record<string, unknown>): Record<string, unknown> {
  const kind = target.kind
  if (kind === 'document') return { kind, document_id: target.documentId }
  if (kind === 'block') return { kind, document_id: target.documentId, block_id: target.blockId, source_revision_id: target.sourceRevisionId ?? null }
  if (kind === 'search') return { kind, query: target.query, search_mode: target.searchMode ?? 'text', space_ids: target.spaceIds ?? [], authority_kinds: target.authorityKinds ?? [], tags: target.tags ?? [] }
  if (kind === 'graph') return { kind, root_document_id: target.rootDocumentId ?? null, space_ids: target.spaceIds ?? [], relation_kinds: target.relationKinds ?? [], viewport: target.viewport ?? { x: 0, y: 0, zoom: 1 } }
  return { kind, workspace_id: target.workspaceId }
}
function targetFromWire(target: z.infer<typeof knowledgeTargetSchema>): Record<string, unknown> {
  if (target.kind === 'document') return { kind: target.kind, documentId: target.document_id }
  if (target.kind === 'block') return { kind: target.kind, documentId: target.document_id, blockId: target.block_id, sourceRevisionId: target.source_revision_id ?? null }
  if (target.kind === 'search') return { kind: target.kind, query: target.query, searchMode: target.search_mode, spaceIds: target.space_ids, authorityKinds: target.authority_kinds, tags: target.tags }
  if (target.kind === 'graph') return { kind: target.kind, rootDocumentId: target.root_document_id, spaceIds: target.space_ids, relationKinds: target.relation_kinds, viewport: target.viewport }
  return { kind: target.kind, workspaceId: target.workspace_id }
}
export interface KnowledgeBookmark { id: string; targetKind: z.infer<typeof targetKind>; target: Record<string, unknown>; displayLabel: string; targetState?: z.infer<typeof targetState> }
function bookmarkFromWire(value: z.infer<typeof bookmarkMutationWireSchema> | z.infer<typeof bookmarkWireSchema>): KnowledgeBookmark {
  return { id: value.id, targetKind: value.target_kind, target: targetFromWire(value.target), displayLabel: value.display_label, ...('target_state' in value ? { targetState: value.target_state } : {}) }
}
export function parseBookmark(value: unknown): KnowledgeBookmark { return bookmarkFromWire(parse(bookmarkWireSchema, value)) }
export function parseBookmarkFolder(value: unknown) { preflightFolderTree(value); return parse(bookmarkFolderWireSchema, value) }

const bookmarkCommandSchema = z.object({ operationId: localId.optional(), target: z.object({ kind: targetKind }).passthrough(), displayLabel: z.string().min(1).max(512), authorityKind: authority.nullable(), spaceId: id('knowledge_engine_space').nullable(), folderId: id('knowledge_bookmark_folder').nullable(), tags: z.array(z.string().min(1).max(128)).max(32), position: z.number().int().nonnegative() }).strict()
function bookmarkCommandToWire(command: unknown): Record<string, unknown> {
  const parsed = bookmarkCommandSchema.parse(command)
  return { operation_id: parsed.operationId ?? createKnowledgeNavigationOperationId(), target: targetToWire(parsed.target), display_label: parsed.displayLabel, authority_kind: parsed.authorityKind, space_id: parsed.spaceId, folder_id: parsed.folderId, tags: parsed.tags, position: parsed.position }
}
const bookmarkUpdateCommandSchema = z.object({ operationId: localId.optional(), expectedRevision: z.number().int().min(1), target: z.object({ kind: targetKind }).passthrough().optional(), displayLabel: z.string().min(1).max(512).optional(), authorityKind: authority.nullable().optional(), spaceId: id('knowledge_engine_space').nullable().optional(), folderId: id('knowledge_bookmark_folder').nullable().optional(), tags: z.array(z.string().min(1).max(128)).max(32).optional(), position: z.number().int().nonnegative().optional() }).strict()
function bookmarkUpdateCommandToWire(command: unknown): Record<string, unknown> {
  const parsed = bookmarkUpdateCommandSchema.parse(command)
  return { operation_id: parsed.operationId ?? createKnowledgeNavigationOperationId(), expected_revision: parsed.expectedRevision, ...(parsed.target ? { target: targetToWire(parsed.target) } : {}), ...(parsed.displayLabel !== undefined ? { display_label: parsed.displayLabel } : {}), ...(parsed.authorityKind !== undefined ? { authority_kind: parsed.authorityKind } : {}), ...(parsed.spaceId !== undefined ? { space_id: parsed.spaceId } : {}), ...(parsed.folderId !== undefined ? { folder_id: parsed.folderId } : {}), ...(parsed.tags !== undefined ? { tags: parsed.tags } : {}), ...(parsed.position !== undefined ? { position: parsed.position } : {}) }
}
// Legacy endpoints below are deliberately shallow until their individual DTOs are
// consumed by UI.  Record maps (notably panes) stay intact rather than being
// recursively rewritten as field names.
function camel(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase()), item]))
}
function wire(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`), item]))
}
function withOperation<T extends Record<string, unknown>>(command: T): T & { operation_id: string } {
  const operationId = (command.operationId as string | undefined) ?? createKnowledgeNavigationOperationId()
  return { ...wire(command) as T, operation_id: operationId }
}

export const knowledgeNavigationApi = {
  listBookmarks: async (filters: { cursor?: string; limit?: number; folderId?: string; tags?: string[]; targetKinds?: string[]; spaceIds?: string[]; authorityKinds?: string[] } = {}) => {
    const params = { ...(filters.cursor ? { cursor: filters.cursor } : {}), ...(filters.limit ? { limit: filters.limit } : {}), ...(filters.folderId ? { folder_id: filters.folderId } : {}), ...(filters.tags ? { tag: filters.tags } : {}), ...(filters.targetKinds ? { target_kind: filters.targetKinds } : {}), ...(filters.spaceIds ? { space_id: filters.spaceIds } : {}), ...(filters.authorityKinds ? { authority_kind: filters.authorityKinds } : {}) }
    const result = parse(z.object({ items: z.array(bookmarkWireSchema), next_cursor: z.string().nullable() }).strict(), (await apiClient.get(`${navigationPath}/bookmarks`, { params })).data)
    return { items: result.items.map(bookmarkFromWire), nextCursor: result.next_cursor }
  },
  createBookmark: async (command: z.input<typeof bookmarkCommandSchema>) => bookmarkFromWire(parse(bookmarkMutationWireSchema, (await apiClient.post(`${navigationPath}/bookmarks`, bookmarkCommandToWire(command))).data)),
  updateBookmark: async (bookmarkId: string, command: z.input<typeof bookmarkUpdateCommandSchema>) => bookmarkFromWire(parse(bookmarkMutationWireSchema, (await apiClient.patch(`${navigationPath}/bookmarks/${encodeURIComponent(bookmarkId)}`, bookmarkUpdateCommandToWire(command))).data)),
  deleteBookmark: async (bookmarkId: string, command: Record<string, unknown>) => camel(parse(receiptSchema, (await apiClient.delete(`${navigationPath}/bookmarks/${encodeURIComponent(bookmarkId)}`, { data: withOperation(command) })).data)),
  listFolders: async () => camel(parse(z.object({ items: z.array(bookmarkFolderWireSchema) }).strict(), (await apiClient.get(`${navigationPath}/bookmark-folders`)).data)),
  createFolder: async (command: Record<string, unknown>) => camel(parse(bookmarkFolderWireSchema, (await apiClient.post(`${navigationPath}/bookmark-folders`, withOperation(command))).data)),
  updateFolder: async (folderId: string, command: Record<string, unknown>) => camel(parse(bookmarkFolderWireSchema, (await apiClient.patch(`${navigationPath}/bookmark-folders/${encodeURIComponent(folderId)}`, withOperation(command))).data)),
  deleteFolder: async (folderId: string, command: Record<string, unknown>) => camel(parse(receiptSchema, (await apiClient.delete(`${navigationPath}/bookmark-folders/${encodeURIComponent(folderId)}`, { data: withOperation(command) })).data)),
  listWorkspaces: async () => camel(parse(z.object({ items: z.array(workspaceSummarySchema) }).strict(), (await apiClient.get(`${navigationPath}/workspaces`)).data)),
  createWorkspace: async (command: Record<string, unknown>) => camel(parse(workspaceWireSchema, (await apiClient.post(`${navigationPath}/workspaces`, withOperation(command))).data)),
  getWorkspace: async (workspaceId: string) => camel(parse(workspaceWireSchema, (await apiClient.get(`${navigationPath}/workspaces/${encodeURIComponent(workspaceId)}`)).data)),
  updateWorkspace: async (workspaceId: string, command: Record<string, unknown>) => camel(parse(workspaceWireSchema, (await apiClient.patch(`${navigationPath}/workspaces/${encodeURIComponent(workspaceId)}`, withOperation(command))).data)),
  duplicateWorkspace: async (workspaceId: string, command: Record<string, unknown>) => camel(parse(workspaceWireSchema, (await apiClient.post(`${navigationPath}/workspaces/${encodeURIComponent(workspaceId)}/duplicate`, withOperation(command))).data)),
  deleteWorkspace: async (workspaceId: string, command: Record<string, unknown>) => camel(parse(receiptSchema, (await apiClient.delete(`${navigationPath}/workspaces/${encodeURIComponent(workspaceId)}`, { data: withOperation(command) })).data)),
  restorePlan: async (workspaceId: string, revision: number) => camel(parse(restorePlanWireSchema, (await apiClient.post(`${navigationPath}/workspaces/${encodeURIComponent(workspaceId)}/restore-plan`, { revision })).data)),
  randomNote: async (filters: Record<string, unknown> = {}) => camel(parse(randomNoteWireSchema, (await apiClient.post(`${navigationPath}/random-note`, wire(filters))).data)),
}
