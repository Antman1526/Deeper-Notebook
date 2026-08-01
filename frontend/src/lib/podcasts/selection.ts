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
const authorityKind = z.enum(['app_owned', 'external_read_only'])
const visibleQuery = z.string().min(1).max(512).refine(
  (value) => !/^(?:[\\/]|[A-Za-z]:[\\/])/.test(value) && !value.includes('\0'),
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
