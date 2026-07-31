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

const descriptorSchema = z.object({
  document_id: id('knowledge_engine_document'), space_id: id('knowledge_engine_space'), authority_kind: authority,
  source_kind: z.enum(['overlay', 'obsidian', 'logseq', 'markdown']), title: z.string().min(1).max(4096),
  relative_locator: z.string().min(1).max(4096), legacy_note_id: z.string().min(1).max(128), legacy_container_id: z.string().min(1).max(128),
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
export const bookmarkWireSchema = bookmarkBase.extend({ target_state: targetState, target_document: descriptorSchema.nullable() }).strict()
export const bookmarkFolderWireSchema = z.object({ schema_version: z.literal(1), id: id('knowledge_bookmark_folder'), name: z.string().min(1).max(256), name_key: z.string().min(1).max(256), parent_folder_id: id('knowledge_bookmark_folder').nullable(), position: z.number().int().nonnegative(), revision: z.number().int().min(1), created_at: z.string(), updated_at: z.string(), children: z.array(z.unknown()).optional() }).strict()
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

function camel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(camel)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase()), camel(item)]))
}
function wire(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(wire)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`), wire(item)]))
}
function parse<T>(schema: z.ZodType<T>, value: unknown): T { structuralPathCheck(value); return schema.parse(value) }
export function createKnowledgeNavigationOperationId(): string { return crypto.randomUUID() }
function withOperation<T extends Record<string, unknown>>(command: T): T & { operation_id: string } {
  const operation = command as Record<string, unknown>
  const stableOperationId = (operation.operationId as string | undefined) ?? createKnowledgeNavigationOperationId()
  if (!operation.operationId) operation.operationId = stableOperationId
  return { ...wire(command) as T, operation_id: stableOperationId }
}

export type KnowledgeBookmark = ReturnType<typeof parseBookmark>
export function parseBookmark(value: unknown) { return camel(parse(bookmarkWireSchema, value)) as z.infer<typeof bookmarkWireSchema> }
export function parseBookmarkFolder(value: unknown) { return camel(parse(bookmarkFolderWireSchema, value)) as z.infer<typeof bookmarkFolderWireSchema> }

export const knowledgeNavigationApi = {
  listBookmarks: async (filters: Record<string, unknown> = {}) => camel(parse(z.object({ items: z.array(bookmarkWireSchema), next_cursor: z.string().nullable() }).strict(), (await apiClient.get(`${navigationPath}/bookmarks`, { params: wire(filters) })).data)),
  createBookmark: async (command: Record<string, unknown>) => camel(parse(bookmarkWireSchema, (await apiClient.post(`${navigationPath}/bookmarks`, withOperation(command))).data)),
  updateBookmark: async (bookmarkId: string, command: Record<string, unknown>) => camel(parse(bookmarkWireSchema, (await apiClient.patch(`${navigationPath}/bookmarks/${encodeURIComponent(bookmarkId)}`, withOperation(command))).data)),
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
