import axios from 'axios'
import { z } from 'zod'

import apiClient from './client'
import { canonicalVaultRelativePathSchema } from './knowledge-workspace'

const vaultPrefix = '/deeper-notebook/vaults'

export const vaultFileSchema = z.object({
  id: z.string(),
  note_id: z.string(),
  vault_id: z.string(),
  relative_path: canonicalVaultRelativePathSchema,
  file_kind: z.string(),
  format: z.enum(['obsidian', 'logseq', 'markdown']),
  content_hash: z.string().nullable(),
  parse_status: z.enum(['pending', 'parsed', 'unsupported', 'invalid', 'conflict', 'missing']),
  size_bytes: z.number().int().nonnegative(),
  modified_ns: z.number().int().nonnegative(),
  encoding: z.string().nullable(),
  newline: z.enum(['lf', 'crlf', 'mixed', 'none']).nullable(),
  deleted_state: z.enum(['present', 'missing']),
}).passthrough()

export const vaultMountSchema = z.object({
  id: z.string(), name: z.string(), format_mode: z.enum(['obsidian', 'logseq', 'mixed', 'markdown']),
  state: z.string(), parent_vault_id: z.string().nullable().optional(), watch_enabled: z.boolean(),
}).passthrough()

export const vaultLinkSchema = z.object({
  id: z.string(),
  source_note_id: z.string(),
  target_note_id: z.string().nullable(),
  target_note_title: z.string().nullable().optional(),
  target_relative_path: canonicalVaultRelativePathSchema.nullable().optional(),
  target_text: z.string(),
  source_note_title: z.string().nullable().optional(),
  target_heading: z.string().nullable().optional(),
  alias: z.string().nullable().optional(),
  link_kind: z.string(),
  resolved: z.boolean(),
  source_start: z.number().int().nonnegative(),
  source_end: z.number().int().nonnegative(),
}).passthrough().superRefine((link, context) => {
  if (link.resolved && (
    !link.target_note_id
    || link.target_note_title == null
    || link.target_relative_path == null
  )) {
    context.addIssue({
      code: 'custom',
      message: 'resolved link is missing canonical target identity',
    })
  }
  if (link.source_end < link.source_start) {
    context.addIssue({
      code: 'custom',
      message: 'source_end must not precede source_start',
    })
  }
})

export const vaultBlockSchema = z.object({
  markdown: z.string().optional(),
  heading_path: z.array(z.string()).optional(),
  block_kind: z.string().optional(),
  properties: z.record(z.string(), z.unknown()).optional(),
}).passthrough()

export const vaultPageSchema = z.object({
  file: vaultFileSchema,
  note: z.object({ id: z.string(), title: z.string().nullable().optional(), markdown: z.string().optional(), content: z.string().optional(), source_format: z.string().optional(), external_state: z.string().optional(), properties: z.record(z.string(), z.unknown()).optional(), tags: z.array(z.string()).optional() }).passthrough(),
  blocks: z.array(vaultBlockSchema),
  tasks: z.array(z.unknown()), outgoing_links: z.array(vaultLinkSchema), backlinks: z.array(vaultLinkSchema),
}).passthrough()

export const vaultGraphSchema = z.object({
  nodes: z.array(z.object({ id: z.string(), title: z.string().nullable().optional(), source_format: z.string().nullable().optional(), external_state: z.string().nullable().optional() }).passthrough()),
  edges: z.array(z.object({ id: z.string(), source: z.string(), target: z.string(), kind: z.string().optional(), resolved: z.boolean().optional() }).passthrough()),
})

export const vaultScanSchema = z.object({
  operation_id: z.string(), state: z.string(), observed: z.number(), parsed: z.number(), unchanged: z.number(), unsupported: z.number(), invalid: z.number(), missing: z.number(), embeddings_pending: z.number(),
})

export type VaultFile = z.infer<typeof vaultFileSchema>
export type VaultMount = z.infer<typeof vaultMountSchema>
export type VaultPage = z.infer<typeof vaultPageSchema>
export type VaultLink = z.infer<typeof vaultLinkSchema>
export type VaultGraph = z.infer<typeof vaultGraphSchema>

function isPathBearingField(key: string): boolean {
  const normalized = key
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
  if (normalized === 'heading_path' || normalized === 'heading_paths') {
    return false
  }
  return normalized === 'path'
    || normalized === 'paths'
    || normalized.endsWith('_path')
    || normalized.endsWith('_paths')
}

function assertNoAbsolutePath(value: unknown): void {
  const stack: Array<{ value: unknown; pathBearing: boolean }> = [{
    value,
    pathBearing: false,
  }]
  const visitedByContext = [
    new WeakSet<object>(),
    new WeakSet<object>(),
  ]

  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) break
    if (typeof current.value === 'string') {
      if (
        current.pathBearing
        && /^(?:[\\/]|[A-Za-z]:[\\/])/.test(current.value)
      ) {
        throw new Error('Vault response contained an absolute path')
      }
      continue
    }
    if (!current.value || typeof current.value !== 'object') continue

    const visited = visitedByContext[current.pathBearing ? 1 : 0]
    if (visited.has(current.value)) continue
    visited.add(current.value)

    if (Array.isArray(current.value)) {
      for (const item of current.value) {
        stack.push({ value: item, pathBearing: current.pathBearing })
      }
      continue
    }
    for (const [key, item] of Object.entries(current.value)) {
      stack.push({
        value: item,
        pathBearing: current.pathBearing || isPathBearingField(key),
      })
    }
  }
}

function safeParse<T>(schema: z.ZodType<T>, data: unknown): T {
  assertNoAbsolutePath(data)
  return schema.parse(data)
}

export type VaultPageContractErrorCode =
  | 'page-invalid'
  | 'canonical-path-unavailable'

export class VaultPageContractError extends Error {
  constructor(public readonly code: VaultPageContractErrorCode) {
    super(code)
    this.name = 'VaultPageContractError'
  }
}

function parseRequestedPage(
  vaultId: string,
  noteId: string,
  data: unknown,
): VaultPage {
  const canonicalFile = z.object({
    file: z.object({
      relative_path: canonicalVaultRelativePathSchema,
    }).passthrough(),
  }).passthrough().safeParse(data)
  if (!canonicalFile.success) {
    throw new VaultPageContractError('canonical-path-unavailable')
  }
  try {
    assertNoAbsolutePath(data)
  } catch {
    throw new VaultPageContractError('page-invalid')
  }
  const parsed = vaultPageSchema.safeParse(data)
  if (!parsed.success) {
    throw new VaultPageContractError('page-invalid')
  }
  const page = parsed.data
  if (
    page.file.vault_id !== vaultId
    || page.file.note_id !== noteId
    || page.note.id !== noteId
  ) {
    throw new VaultPageContractError('page-invalid')
  }
  if (!/^[0-9a-f]{64}$/i.test(page.file.content_hash ?? '')) {
    throw new VaultPageContractError('page-invalid')
  }
  return page
}

async function getRequestedPage(vaultId: string, noteId: string): Promise<VaultPage> {
  try {
    const response = await apiClient.get(
      `${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}`,
    )
    return parseRequestedPage(vaultId, noteId, response.data)
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const code = error.response?.data?.detail?.code
      if (code === 'vault_canonical_file_unavailable') {
        throw new VaultPageContractError('canonical-path-unavailable')
      }
      if (code === 'vault_page_invalid') {
        throw new VaultPageContractError('page-invalid')
      }
    }
    throw error
  }
}

export const vaultApi = {
  list: async () => safeParse(z.array(vaultMountSchema), (await apiClient.get(`${vaultPrefix}`)).data),
  detail: async (vaultId: string) => safeParse(vaultMountSchema, (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}`)).data),
  files: async (vaultId: string) => safeParse(z.array(vaultFileSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/files`)).data),
  page: getRequestedPage,
  backlinks: async (vaultId: string, noteId: string) => safeParse(z.array(vaultLinkSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}/backlinks`)).data),
  outgoing: async (vaultId: string, noteId: string) => safeParse(z.array(vaultLinkSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}/outgoing`)).data),
  graph: async (vaultId: string, noteId: string) => safeParse(vaultGraphSchema, (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/graph`, { params: { center_note_id: noteId, depth: 2 } })).data),
  scan: async (vaultId: string) => safeParse(vaultScanSchema, (await apiClient.post(`${vaultPrefix}/${encodeURIComponent(vaultId)}/scan`)).data),
}
