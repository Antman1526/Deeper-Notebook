import { z } from 'zod'

const engineId = (prefix: string) => z.string()
  .regex(new RegExp(`^${prefix}:[A-Za-z0-9_-]+$`))
  .max(128)

const notebookId = engineId('notebook')
const noteId = engineId('note')
const sourceId = engineId('source')
const documentId = engineId('knowledge_engine_document')
const blockId = engineId('knowledge_engine_block')
const revisionId = engineId('knowledge_engine_(?:revision|source_revision)')
const spaceId = engineId('knowledge_engine_space')
const bookmarkId = engineId('knowledge_bookmark')
const folderId = engineId('knowledge_bookmark_folder')
const workspaceId = engineId('named_knowledge_workspace')
const embeddedFileUrl = /\bfile:\/\/[^\s,;\)\]}>]*/i
const embeddedWindowsPath = /(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s,;\)\]}>]*/
const embeddedUncPath = /(?:^|(?<=[\s("'=]))(?:\\\\|\/\/)[^\s,;\)\]}>]*/
const embeddedPosixPath = /(?:^|(?<=[\s("'=:]))\/(?!\/)[^\s,;\)\]}>]*/
const authorityKind = z.enum(['app_owned', 'external_read_only'])
const visibleQuery = z.string().min(1).max(512).refine(
  (value) => !embeddedFileUrl.test(value)
    && !embeddedWindowsPath.test(value)
    && !embeddedUncPath.test(value)
    && !embeddedPosixPath.test(value)
    && !value.includes('\0'),
  'A podcast selection cannot contain an absolute path',
)

const collectionSelectionSchema = z.object({
  kind: z.literal('knowledge_collection'),
  collectionKind: z.enum(['folder', 'bookmark', 'workspace']),
  collectionId: z.union([folderId, bookmarkId, workspaceId]),
}).strict().superRefine((value, context) => {
  const prefix = {
    folder: 'knowledge_bookmark_folder:',
    bookmark: 'knowledge_bookmark:',
    workspace: 'named_knowledge_workspace:',
  }[value.collectionKind]
  if (!value.collectionId.startsWith(prefix)) {
    context.addIssue({ code: 'custom', message: 'collection ID does not match kind' })
  }
})

export const podcastSelectionSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('notebook'), notebookId }).strict(),
  z.object({ kind: z.literal('app_note'), noteId }).strict(),
  z.object({
    kind: z.literal('app_source'), sourceId,
    inclusionMode: z.enum(['insights', 'full']).default('full'),
  }).strict(),
  z.object({
    kind: z.literal('knowledge_document'), documentId,
    expectedRevisionId: revisionId.nullish(),
  }).strict(),
  z.object({
    kind: z.literal('knowledge_block'), documentId, blockId,
    expectedRevisionId: revisionId.nullish(),
    sourceStart: z.number().int().nonnegative().nullish(),
    sourceEnd: z.number().int().nonnegative().nullish(),
  }).strict().superRefine((value, context) => {
    if ((value.sourceStart == null) !== (value.sourceEnd == null)) {
      context.addIssue({ code: 'custom', message: 'both selection offsets are required' })
    }
    if (value.sourceStart != null && value.sourceEnd != null && value.sourceEnd <= value.sourceStart) {
      context.addIssue({ code: 'custom', message: 'selection range must have positive length' })
    }
  }),
  collectionSelectionSchema,
  z.object({
    kind: z.literal('saved_search'), query: visibleQuery,
    searchMode: z.enum(['exact', 'text', 'semantic']),
    spaceIds: z.array(spaceId).max(32),
    authorityKinds: z.array(authorityKind).max(2),
  }).strict(),
  z.object({
    kind: z.literal('graph_selection'), documentIds: z.array(documentId).min(1).max(128),
  }).strict(),
])

export type PodcastSelection = z.infer<typeof podcastSelectionSchema>
export type PodcastDestination = 'quick' | 'studio'

export function normalizePodcastSelections(selections: PodcastSelection[]): PodcastSelection[] {
  return selections.map((selection) => {
    if (selection.kind === 'graph_selection') {
      return { ...selection, documentIds: [...new Set(selection.documentIds)].sort() }
    }
    if (selection.kind === 'saved_search') {
      return { ...selection, query: selection.query.trim().replace(/\s+/g, ' ') }
    }
    return { ...selection }
  })
}

export function toPodcastSelectionWire(selection: PodcastSelection): Record<string, unknown> {
  switch (selection.kind) {
    case 'notebook':
      return { kind: selection.kind, notebook_id: selection.notebookId }
    case 'app_note':
      return { kind: selection.kind, note_id: selection.noteId }
    case 'app_source':
      return { kind: selection.kind, source_id: selection.sourceId, inclusion_mode: selection.inclusionMode }
    case 'knowledge_document':
      return {
        kind: selection.kind, document_id: selection.documentId,
        expected_revision_id: selection.expectedRevisionId ?? null,
      }
    case 'knowledge_block':
      return {
        kind: selection.kind, document_id: selection.documentId, block_id: selection.blockId,
        expected_revision_id: selection.expectedRevisionId ?? null,
        source_start: selection.sourceStart ?? null, source_end: selection.sourceEnd ?? null,
      }
    case 'knowledge_collection':
      return {
        kind: selection.kind, collection_kind: selection.collectionKind,
        collection_id: selection.collectionId,
      }
    case 'saved_search':
      return {
        kind: selection.kind, query: selection.query, search_mode: selection.searchMode,
        space_ids: selection.spaceIds, authority_kinds: selection.authorityKinds,
      }
    case 'graph_selection':
      return { kind: selection.kind, document_ids: selection.documentIds }
  }
}

/**
 * Convert a backend retry-preview reference through the same strict union as
 * browser-created selections.  The backend intentionally returns snake_case
 * keys; no source body, path, or unknown metadata is accepted here.
 */
export function fromPodcastSelectionWire(value: unknown): PodcastSelection {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid podcast selection wire reference')
  }
  const wire = value as Record<string, unknown>
  const kind = wire.kind
  const allowedKeys: Record<string, string[]> = {
    notebook: ['kind', 'notebook_id'],
    app_note: ['kind', 'note_id'],
    app_source: ['kind', 'source_id', 'inclusion_mode'],
    knowledge_document: ['kind', 'document_id', 'expected_revision_id'],
    knowledge_block: [
      'kind', 'document_id', 'block_id', 'expected_revision_id',
      'source_start', 'source_end',
    ],
    knowledge_collection: ['kind', 'collection_kind', 'collection_id'],
    saved_search: ['kind', 'query', 'search_mode', 'space_ids', 'authority_kinds'],
    graph_selection: ['kind', 'document_ids'],
  }
  if (typeof kind !== 'string' || !allowedKeys[kind]
    || Object.keys(wire).some((key) => !allowedKeys[kind].includes(key))) {
    throw new Error('Invalid podcast selection wire reference')
  }
  let candidate: Record<string, unknown>
  switch (kind) {
    case 'notebook':
      candidate = { kind, notebookId: wire.notebook_id }
      break
    case 'app_note':
      candidate = { kind, noteId: wire.note_id }
      break
    case 'app_source':
      candidate = {
        kind,
        sourceId: wire.source_id,
        inclusionMode: wire.inclusion_mode,
      }
      break
    case 'knowledge_document':
      candidate = {
        kind,
        documentId: wire.document_id,
        expectedRevisionId: wire.expected_revision_id ?? null,
      }
      break
    case 'knowledge_block':
      candidate = {
        kind,
        documentId: wire.document_id,
        blockId: wire.block_id,
        expectedRevisionId: wire.expected_revision_id ?? null,
        sourceStart: wire.source_start ?? null,
        sourceEnd: wire.source_end ?? null,
      }
      break
    case 'knowledge_collection':
      candidate = {
        kind,
        collectionKind: wire.collection_kind,
        collectionId: wire.collection_id,
      }
      break
    case 'saved_search':
      candidate = {
        kind,
        query: wire.query,
        searchMode: wire.search_mode,
        spaceIds: wire.space_ids,
        authorityKinds: wire.authority_kinds,
      }
      break
    case 'graph_selection':
      candidate = { kind, documentIds: wire.document_ids }
      break
    default:
      throw new Error('Invalid podcast selection wire reference')
  }
  return podcastSelectionSchema.parse(candidate)
}

export function fromPodcastSelectionWireList(value: unknown): PodcastSelection[] {
  if (!Array.isArray(value)) {
    throw new Error('Invalid podcast selection wire references')
  }
  return value.map(fromPodcastSelectionWire)
}

// Explicit alias for callers that prefer parser terminology.
export const parsePodcastSelectionWire = fromPodcastSelectionWire
