import { z } from 'zod'

import apiClient from './client'

const vaultPrefix = '/deeper-notebook/vaults'

export const vaultFileSchema = z.object({
  id: z.string(),
  vault_id: z.string(),
  relative_path: z.string(),
  file_kind: z.string(),
  format: z.enum(['obsidian', 'logseq', 'markdown']),
  content_hash: z.string().nullable(),
  parse_status: z.enum(['pending', 'parsed', 'unsupported', 'invalid', 'conflict', 'missing']),
}).passthrough()

export const vaultMountSchema = z.object({
  id: z.string(), name: z.string(), format_mode: z.enum(['obsidian', 'logseq', 'mixed', 'markdown']),
  state: z.string(), parent_vault_id: z.string().nullable().optional(), watch_enabled: z.boolean(),
}).passthrough()

export const vaultLinkSchema = z.object({
  id: z.string(), source_note_id: z.string(), target_note_id: z.string().nullable(), target_text: z.string(),
  target_heading: z.string().nullable().optional(), alias: z.string().nullable().optional(), link_kind: z.string(), resolved: z.boolean(),
}).passthrough()

export const vaultPageSchema = z.object({
  note: z.object({ id: z.string(), title: z.string().nullable().optional(), markdown: z.string().optional(), content: z.string().optional(), source_format: z.string().optional(), external_state: z.string().optional(), properties: z.record(z.string(), z.unknown()).optional(), tags: z.array(z.string()).optional() }).passthrough(),
  blocks: z.array(z.object({ markdown: z.string().optional(), heading_path: z.array(z.string()).optional(), block_kind: z.string().optional(), properties: z.record(z.string(), z.unknown()).optional() }).passthrough()),
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

function assertNoAbsolutePath(value: unknown): void {
  if (typeof value === 'string') {
    if (/^(?:\/|[A-Za-z]:[\\/])/.test(value)) throw new Error('Vault response contained an absolute path')
    return
  }
  if (Array.isArray(value)) value.forEach(assertNoAbsolutePath)
  else if (value && typeof value === 'object') Object.values(value).forEach(assertNoAbsolutePath)
}

function safeParse<T>(schema: z.ZodType<T>, data: unknown): T {
  assertNoAbsolutePath(data)
  return schema.parse(data)
}

export const vaultApi = {
  list: async () => safeParse(z.array(vaultMountSchema), (await apiClient.get(`${vaultPrefix}`)).data),
  detail: async (vaultId: string) => safeParse(vaultMountSchema, (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}`)).data),
  files: async (vaultId: string) => safeParse(z.array(vaultFileSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/files`)).data),
  page: async (vaultId: string, noteId: string) => safeParse(vaultPageSchema, (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}`)).data),
  backlinks: async (vaultId: string, noteId: string) => safeParse(z.array(vaultLinkSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}/backlinks`)).data),
  outgoing: async (vaultId: string, noteId: string) => safeParse(z.array(vaultLinkSchema), (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/pages/${encodeURIComponent(noteId)}/outgoing`)).data),
  graph: async (vaultId: string, noteId: string) => safeParse(vaultGraphSchema, (await apiClient.get(`${vaultPrefix}/${encodeURIComponent(vaultId)}/graph`, { params: { center_note_id: noteId, depth: 2 } })).data),
  scan: async (vaultId: string) => safeParse(vaultScanSchema, (await apiClient.post(`${vaultPrefix}/${encodeURIComponent(vaultId)}/scan`)).data),
}
