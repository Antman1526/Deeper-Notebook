import { z } from 'zod'

import apiClient from './client'
import {
  knowledgeSourceAuthoritySchema,
  canonicalVaultRelativePathSchema,
} from './knowledge-workspace'
import {
  vaultBlockSchema,
  vaultGraphSchema,
  vaultLinkSchema,
  vaultNoteSchema,
  vaultTaskSchema,
} from './vault'

const overlayPrefix = '/deeper-notebook/overlay'

export { knowledgeSourceAuthoritySchema }

const calendarDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((value) => {
    const parsed = new Date(`${value}T00:00:00.000Z`)
    return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
  }, 'date_key must be an ISO calendar date')

const visibleTitleSchema = z.string().min(1).max(512)
  .refine((value) => value.trim().length > 0 && !/[\x00-\x1f\x7f]/.test(value), 'title must contain visible text')

const overlayNoteIdSchema = z.string().min(1).max(128)
const idempotencyKeySchema = z.string().min(1).max(128)

export const overlayNoteSchema = z.object({
  id: overlayNoteIdSchema,
  source_authority: z.literal('overlay'),
  space_id: z.string().min(1).max(128),
  projected_note_id: z.string().min(1).max(128),
  stable_id: z.string().min(20).max(128),
  kind: z.enum(['daily', 'unique']),
  date_key: calendarDateSchema.nullable(),
  relative_path: canonicalVaultRelativePathSchema,
  title: visibleTitleSchema,
  content_hash: z.string().regex(/^[0-9a-f]{64}$/),
  revision: z.number().int().min(1),
  projection_state: z.enum(['pending', 'current', 'failed', 'conflict']),
  encoding: z.literal('utf-8'),
  newline: z.literal('lf'),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
}).strict().superRefine((note, context) => {
  if (note.kind === 'daily') {
    if (!note.date_key || note.relative_path !== `Daily/${note.date_key}.md`) {
      context.addIssue({ code: 'custom', message: 'daily overlay note has inconsistent date identity' })
    }
  } else if (note.date_key !== null) {
    context.addIssue({ code: 'custom', message: 'unique overlay note cannot have a date key' })
  }
})

const overlayLinkIdentitySchema = z.object({
  source_overlay_note_id: overlayNoteIdSchema.nullable(),
  target_overlay_note_id: overlayNoteIdSchema.nullable(),
}).passthrough()

export const overlayLinkSchema = z.intersection(
  vaultLinkSchema,
  overlayLinkIdentitySchema,
)

export const overlayPageSchema = z.object({
  overlay: overlayNoteSchema,
  note: vaultNoteSchema,
  blocks: z.array(vaultBlockSchema),
  tasks: z.array(vaultTaskSchema),
  outgoing_links: z.array(overlayLinkSchema),
  backlinks: z.array(overlayLinkSchema),
  graph: vaultGraphSchema.nullable(),
}).strict()

const overlayRootSchema = z.object({
  id: z.string().min(1).max(128),
  source_authority: z.literal('overlay'),
}).strict()

const createUniqueOverlayNoteSchema = z.object({
  title: visibleTitleSchema,
  idempotencyKey: idempotencyKeySchema,
})

const updateOverlayNoteSchema = z.object({
  title: visibleTitleSchema,
  markdown: z.string().max(10 * 1024 * 1024),
  expectedRevision: z.number().int().min(1),
  idempotencyKey: idempotencyKeySchema,
})

export type OverlayNote = z.infer<typeof overlayNoteSchema>
export type OverlayLink = z.infer<typeof overlayLinkSchema>
export type OverlayPage = z.infer<typeof overlayPageSchema>
export type CreateUniqueOverlayNote = z.input<typeof createUniqueOverlayNoteSchema>
export type UpdateOverlayNote = z.input<typeof updateOverlayNoteSchema>

function isAuthoredContentField(key: string): boolean {
  const normalized = key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase()
  return ['content', 'markdown', 'properties', 'tags', 'title', 'titles', 'alias', 'aliases', 'heading', 'headings', 'text', 'texts', 'description', 'descriptions'].includes(normalized)
    || normalized.endsWith('_title') || normalized.endsWith('_titles')
    || normalized.endsWith('_alias') || normalized.endsWith('_aliases')
    || normalized.endsWith('_heading') || normalized.endsWith('_headings')
    || normalized.endsWith('_text') || normalized.endsWith('_texts')
    || normalized.endsWith('_description') || normalized.endsWith('_descriptions')
}

function assertNoAbsolutePath(value: unknown): void {
  const stack: Array<{ value: unknown; structural: boolean }> = [{ value, structural: true }]
  const visited = [new WeakSet<object>(), new WeakSet<object>()]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (typeof current.value === 'string') {
      if (current.structural && /^(?:[\\/]|[A-Za-z]:[\\/])/.test(current.value)) {
        throw new Error('Overlay response contained an absolute path')
      }
      continue
    }
    if (!current.value || typeof current.value !== 'object') continue
    const seen = visited[current.structural ? 1 : 0]
    if (seen.has(current.value)) continue
    seen.add(current.value)
    if (Array.isArray(current.value)) {
      current.value.forEach((item) => stack.push({ value: item, structural: current.structural }))
    } else {
      Object.entries(current.value).forEach(([key, item]) => stack.push({
        value: item,
        structural: current.structural && !isAuthoredContentField(key),
      }))
    }
  }
}

function parsePage(data: unknown, requestedId?: string): OverlayPage {
  assertNoAbsolutePath(data)
  const page = overlayPageSchema.parse(data)
  if (requestedId && page.overlay.id !== requestedId) {
    throw new Error('Overlay page does not match the requested note')
  }
  if (page.note.id !== page.overlay.projected_note_id) {
    throw new Error('Overlay page note does not match the projected note identity')
  }
  return page
}

export const overlayApi = {
  root: async () => overlayRootSchema.parse((await apiClient.get(overlayPrefix)).data),
  list: async (limit = 100, offset = 0) => {
    const response = await apiClient.get(`${overlayPrefix}/notes`, { params: { limit, offset } })
    assertNoAbsolutePath(response.data)
    return z.array(overlayNoteSchema).parse(response.data)
  },
  page: async (id: string) => parsePage(
    (await apiClient.get(`${overlayPrefix}/notes/${encodeURIComponent(overlayNoteIdSchema.parse(id))}`)).data,
    id,
  ),
  daily: async (dateKey: string) => parsePage(
    (await apiClient.put(`${overlayPrefix}/daily/${encodeURIComponent(calendarDateSchema.parse(dateKey))}`)).data,
  ),
  unique: async (input: CreateUniqueOverlayNote) => {
    const request = createUniqueOverlayNoteSchema.parse(input)
    return parsePage((await apiClient.post(`${overlayPrefix}/notes/unique`, {
      title: request.title,
      idempotency_key: request.idempotencyKey,
    })).data)
  },
  update: async (id: string, input: UpdateOverlayNote) => {
    const request = updateOverlayNoteSchema.parse(input)
    return parsePage((await apiClient.put(
      `${overlayPrefix}/notes/${encodeURIComponent(overlayNoteIdSchema.parse(id))}`,
      {
        title: request.title,
        markdown: request.markdown,
        expected_revision: request.expectedRevision,
        idempotency_key: request.idempotencyKey,
      },
    )).data, id)
  },
}
