import { z } from 'zod'

const boundedId = z.string().min(1).max(512).refine((value) => value === value.trim() && !/[\u0000-\u001f\u007f]/.test(value))
const sha256 = z.string().regex(/^[0-9a-f]{64}$/)

export const ankiHttpOptionsSchema = z.object({
  schema_version: z.literal(1).default(1),
  syllabus_unit_id: z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/).nullable().optional(),
  deck_names: z.array(z.string().min(1).max(200)).max(100).default([]),
}).strict()

export const ankiImportPreviewSchema = z.object({
  schema_version: z.literal(1),
  job_id: z.string().regex(/^anki_job:[a-f0-9]{32,64}$/),
  status: z.enum(['preview_ready', 'processing', 'failed', 'published']),
  card_count: z.number().int().min(0).max(10_000),
  transformed_count: z.number().int().min(0).max(10_000),
  skipped_count: z.number().int().min(0).max(10_000),
  rejected_count: z.number().int().min(0).max(10_000),
  package_sha256: sha256,
  collection_member: z.enum(['collection.anki2', 'collection.anki21']),
  message: z.string().max(200).nullable().optional(),
}).strict()

export const ankiImportStatusSchema = ankiImportPreviewSchema.extend({
  receipt_id: z.string().max(512).nullable(),
}).strict()

export const ankiCompatibilityReceiptSchema = z.object({
  schema_version: z.literal(1),
  receipt_id: boundedId,
  plan_id: boundedId,
  request_id: boundedId,
  payload_sha256: sha256,
  package_sha256: sha256,
  collection_sha256: sha256,
  collection_member: z.enum(['collection.anki2', 'collection.anki21']),
  card_count: z.number().int().min(0).max(10_000),
  transformed_count: z.number().int().min(0).max(10_000),
  skipped_count: z.number().int().min(0).max(10_000),
  card_ids: z.array(boundedId).max(10_000),
  deck_names: z.array(z.string().min(1).max(200)).max(1_000),
  tags: z.array(z.string().min(1).max(128)).max(1_000),
  media_names: z.array(z.string().min(1).max(512)).max(500),
  syllabus_unit_id: z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/).nullable(),
  created_at: z.string().datetime({ offset: true }),
}).strict()

export const ankiImportPublishSchema = z.object({
  schema_version: z.literal(1),
  status: z.enum(['published', 'replayed']),
  receipt: ankiCompatibilityReceiptSchema,
}).strict()

export const ankiExportReceiptSchema = z.object({
  schema_version: z.literal(1),
  receipt_id: boundedId,
  plan_id: boundedId,
  plan_revision: z.number().int().min(1),
  syllabus_version: z.number().int().min(1),
  package_sha256: sha256,
  card_count: z.number().int().min(0).max(10_000),
  stable_note_guids: z.array(z.string().regex(/^[0-9a-f]{32}$/)).max(10_000),
  stable_model_ids: z.array(z.number().int().positive()).max(16),
  stable_deck_ids: z.array(z.number().int().positive()).max(1_000),
  created_at: z.string().datetime({ offset: true }),
}).strict()

export const ankiExportResponseSchema = z.object({
  schema_version: z.literal(1),
  download_id: z.string().regex(/^anki_download:[a-f0-9]{32,64}$/),
  receipt: ankiExportReceiptSchema,
}).strict()

export type AnkiHttpOptions = z.infer<typeof ankiHttpOptionsSchema>
export type AnkiImportPreview = z.infer<typeof ankiImportPreviewSchema>
export type AnkiImportStatus = z.infer<typeof ankiImportStatusSchema>
export type AnkiCompatibilityReceipt = z.infer<typeof ankiCompatibilityReceiptSchema>
export type AnkiImportPublish = z.infer<typeof ankiImportPublishSchema>
export type AnkiExportResponse = z.infer<typeof ankiExportResponseSchema>

function invalidResponse(): Error {
  return new Error('Invalid Study Anki response')
}

function decode<T>(schema: z.ZodType<T>, value: unknown): T {
  const parsed = schema.safeParse(value)
  if (!parsed.success) throw invalidResponse()
  return parsed.data
}

export const decodeAnkiImportPreview = (value: unknown) => decode(ankiImportPreviewSchema, value)
export const decodeAnkiImportStatus = (value: unknown) => decode(ankiImportStatusSchema, value)
export const decodeAnkiImportPublish = (value: unknown) => decode(ankiImportPublishSchema, value)
export const decodeAnkiExportResponse = (value: unknown) => decode(ankiExportResponseSchema, value)
