import { z } from 'zod'

const sha256Schema = z.string().regex(/^[0-9a-f]{64}$/)
const dateTimeSchema = z.iso.datetime({ offset: true })
const sourceIdSchema = z.string().regex(/^source:[A-Za-z0-9_-]+$/).max(512)
const commandIdSchema = z.string().min(1).max(512).nullable()
const errorCodeSchema = z.string().regex(/^[a-z0-9][a-z0-9_.-]{0,63}$/).nullable()
const assetUrlSchema = z.string().regex(
  /^\/api\/sources\/source%3A(?:[A-Za-z0-9_.~-]|%[0-9A-F]{2})+\/visual\?v=[0-9a-f]{64}$/,
)

const pageLocatorSchema = z.object({ page: z.number().int().min(1).max(24) }).strict()
const timestampLocatorSchema = z.object({ timestamp_ms: z.number().int().nonnegative() }).strict()
const resourceLocatorSchema = z.object({ resource_id: z.string().trim().min(1).max(128) }).strict()

const visualCommon = {
  source_id: sourceIdSchema,
  content_sha256: sha256Schema,
  asset_sha256: sha256Schema,
  alt_text: z.string().trim().min(1).max(300),
  width: z.number().int().min(1).max(1280),
  height: z.number().int().min(1).max(720),
  mime_type: z.literal('image/webp'),
  asset_url: assetUrlSchema,
  created_at: dateTimeSchema,
  updated_at: dateTimeSchema,
}

const sourceVisualSchema = z.discriminatedUnion('origin', [
  z.object({ ...visualCommon, origin: z.literal('embedded'), source_locator: z.union([pageLocatorSchema, resourceLocatorSchema]) }).strict(),
  z.object({ ...visualCommon, origin: z.literal('video_frame'), source_locator: timestampLocatorSchema }).strict(),
  z.object({ ...visualCommon, origin: z.literal('audio_artwork'), source_locator: resourceLocatorSchema }).strict(),
]).superRefine((value, context) => {
  const expectedPrefix = `/api/sources/${encodeURIComponent(value.source_id)}/visual?v=`
  if (!value.asset_url.startsWith(expectedPrefix)) {
    context.addIssue({
      code: 'custom',
      path: ['asset_url'],
      message: 'asset URL must match its source receipt',
    })
  }
})

const sourceVisualStatusSchema = z.object({
  // v0.8.86 — 'disabled' = backend capability sentinel: the feature flag
  // is off server-side, so mutation actions can never succeed this session.
  state: z.enum(['queued', 'processing', 'unavailable', 'failed', 'disabled']),
  command_id: commandIdSchema.optional().default(null),
  error_code: errorCodeSchema.optional().default(null),
  updated_at: dateTimeSchema,
}).strict()

export const sourceVisualJobSchema = z.object({
  source_id: sourceIdSchema,
  command_id: commandIdSchema,
  content_sha256: sha256Schema,
  asset_sha256: sha256Schema.nullable(),
  origin: z.enum(['embedded', 'video_frame', 'audio_artwork']).nullable(),
  width: z.number().int().min(1).max(1280).nullable(),
  height: z.number().int().min(1).max(720).nullable(),
  duration_ms: z.number().int().min(0).max(60_000).nullable(),
  outcome: z.enum(['queued', 'replayed', 'deleted', 'failed']),
  error_code: errorCodeSchema,
}).strict()

const assetSchema = z.object({
  file_path: z.string().optional().nullable(),
  url: z.string().optional().nullable(),
}).strict()

const sourceBaseShape = {
  id: sourceIdSchema,
  title: z.string().nullable(),
  topics: z.array(z.string()).nullable().optional(),
  provenance: z.record(z.string(), z.unknown()).optional(),
  source_type: z.string().nullable().optional(),
  notebook_count: z.number().int().nonnegative().optional(),
  is_shared: z.boolean().optional(),
  asset: assetSchema.nullable(),
  embedded: z.boolean(),
  embedded_chunks: z.number().int().nonnegative(),
  insights_count: z.number().int().nonnegative(),
  summary_preview: z.string().nullable().optional(),
  created: z.string().nullable(),
  updated: z.string().nullable(),
  file_available: z.boolean().nullable().optional(),
  extracted_char_count: z.number().int().nonnegative().nullable().optional(),
  extraction_quality: z.enum(['pending', 'no_text', 'low_text', 'ok']).nullable().optional(),
  command_id: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  processing_info: z.record(z.string(), z.unknown()).nullable().optional(),
  visual: z.unknown().optional(),
  visual_status: z.unknown().optional(),
}

const sourceListSchema = z.object(sourceBaseShape).strict()
const sourceDetailSchema = z.object({
  ...sourceBaseShape,
  full_text: z.string().nullable(),
  notebooks: z.array(z.string()).nullable().optional(),
}).strict()

export type SourceVisualReceipt = z.infer<typeof sourceVisualSchema>
export type SourceVisualStatus = z.infer<typeof sourceVisualStatusSchema>
export type SourceVisualJob = z.infer<typeof sourceVisualJobSchema>

export function decodeSourceVisual(value: unknown): SourceVisualReceipt {
  return sourceVisualSchema.parse(value)
}

export function decodeSourceVisualStatus(value: unknown): SourceVisualStatus {
  return sourceVisualStatusSchema.parse(value)
}

export function decodeSourceWithVisual(
  value: unknown,
  kind: 'list' | 'detail' = 'list',
) {
  const source = (kind === 'detail' ? sourceDetailSchema : sourceListSchema).parse(value)
  const visual = sourceVisualSchema.safeParse(source.visual)
  const visualStatus = sourceVisualStatusSchema.safeParse(source.visual_status)
  return {
    ...source,
    visual: visual.success && visual.data.source_id === source.id ? visual.data : null,
    visual_status: visualStatus.success ? visualStatus.data : null,
  }
}

export function decodeSourceBearingVisual<T extends object>(value: T): T & {
  visual: SourceVisualReceipt | null
  visual_status: SourceVisualStatus | null
} {
  const candidate = value as T & { visual?: unknown; visual_status?: unknown }
  const visual = sourceVisualSchema.safeParse(candidate.visual)
  const visualStatus = sourceVisualStatusSchema.safeParse(candidate.visual_status)
  const id = 'id' in candidate && typeof candidate.id === 'string' ? candidate.id : ''
  const parentId = 'parent_id' in candidate && typeof candidate.parent_id === 'string' ? candidate.parent_id : ''
  const expectedSourceId = id.startsWith('source:')
    ? id
    : id.startsWith('source_insight:') && parentId.startsWith('source:')
      ? parentId
      : null
  return {
    ...value,
    visual: visual.success && visual.data.source_id === expectedSourceId ? visual.data : null,
    visual_status: visualStatus.success ? visualStatus.data : null,
  }
}

const captureLinkedSourceSchema = z.object({
  id: sourceIdSchema,
  visual: z.unknown(),
}).strict()

export function decodeCaptureLinkedSource(value: unknown): {
  id: string
  visual: SourceVisualReceipt | null
} | null {
  if (value === null || value === undefined) return null
  const linked = captureLinkedSourceSchema.parse(value)
  const visual = sourceVisualSchema.safeParse(linked.visual)
  return { id: linked.id, visual: visual.success && visual.data.source_id === linked.id ? visual.data : null }
}

const searchResultSchema = z.object({
  id: z.string().min(1).max(512),
  title: z.string().nullable().optional().transform(value => value ?? ''),
  parent_id: z.string().optional().default(''),
  final_score: z.number().finite().optional().default(0),
  matches: z.array(z.string()).optional(),
  relevance: z.number().finite().optional(),
  similarity: z.number().finite().optional(),
  score: z.number().finite().optional(),
  type: z.string().optional(),
  source_type: z.string().optional(),
  created: z.string().optional().default(''),
  updated: z.string().optional().default(''),
  visual: z.unknown().optional(),
  visual_status: z.unknown().optional(),
  vault_provenance: z.object({
    canonical_external: z.literal(true),
    vault_id: z.string().min(1).max(512),
    relative_path: z.string().min(1).max(4096),
    source_hash: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  }).strict().optional(),
}).strict()

const searchResponseSchema = z.object({
  results: z.array(searchResultSchema).max(1000),
  total_count: z.number().int().nonnegative(),
  search_type: z.string().min(1).max(64),
}).strict()

export function decodeSearchResponse(value: unknown) {
  const response = searchResponseSchema.parse(value)
  return {
    ...response,
    results: response.results.map(result => decodeSourceBearingVisual(result)),
  }
}

const captureItemSchema = z.object({
  id: z.string().nullable(),
  root_path: z.string(),
  relative_path: z.string(),
  filename: z.string(),
  extension: z.string(),
  state: z.enum(['pending', 'ready', 'importing', 'imported', 'duplicate', 'ignored', 'failed']),
  sha256: sha256Schema.nullable(),
  byte_size: z.number().int().nonnegative().nullable(),
  modified_ns: z.number().int().nonnegative().nullable(),
  reason: z.string().nullable(),
  linked_source: z.unknown().optional(),
}).strict()

const captureScanResponseSchema = z.object({ items: z.array(captureItemSchema).max(200) }).strict()

function decodedCaptureItem(item: z.infer<typeof captureItemSchema>) {
  return { ...item, linked_source: decodeCaptureLinkedSource(item.linked_source) }
}

export function decodeCaptureItems(value: unknown) {
  return z.array(captureItemSchema).max(200).parse(value).map(decodedCaptureItem)
}

export function decodeCaptureScanResponse(value: unknown) {
  const response = captureScanResponseSchema.parse(value)
  return { ...response, items: response.items.map(decodedCaptureItem) }
}
