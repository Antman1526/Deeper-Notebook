import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { canonicalVaultRelativePathSchema } from '@/lib/api/knowledge-workspace'
import type { VaultFile, VaultMount } from '@/lib/api/vault'
import type { SearchResult } from '@/lib/types/search'

export interface KnowledgeCatalogCandidate {
  key: string
  vaultId: string
  noteId: string
  vaultName: string
  format: VaultFile['format']
  title: string
  relativePath: string
  isOpen: boolean
}

function normalized(value: string): string {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

function compareCodePoints(left: string, right: string): number {
  if (left === right) return 0
  return left < right ? -1 : 1
}

function titleFromPath(relativePath: string): string {
  return relativePath.split('/').at(-1)?.replace(/\.md$/iu, '') || relativePath
}

export function buildKnowledgeCatalog(
  mounts: VaultMount[],
  filesByVault: ReadonlyMap<string, readonly VaultFile[]>,
  openTabs: readonly OpenKnowledgeTab[],
): KnowledgeCatalogCandidate[] {
  const open = new Set(openTabs.map(tab => `${tab.vaultId}\0${tab.noteId}`))
  return mounts.flatMap(mount => (filesByVault.get(mount.id) || [])
    .filter(file => file.deleted_state === 'present' && file.parse_status === 'parsed')
    .map(file => ({
      key: `${file.vault_id}\0${file.note_id}`,
      vaultId: file.vault_id,
      noteId: file.note_id,
      vaultName: mount.name,
      format: file.format,
      title: titleFromPath(file.relative_path),
      relativePath: file.relative_path,
      isOpen: open.has(`${file.vault_id}\0${file.note_id}`),
    })))
    .sort((a, b) => compareCodePoints(a.key, b.key))
}

function score(candidate: KnowledgeCatalogCandidate, query: string): number {
  const title = normalized(candidate.title)
  const path = normalized(candidate.relativePath)
  const vault = normalized(candidate.vaultName)
  if (!query) return 10
  if (title === query) return 600
  if (title.startsWith(query)) return 500
  if (title.split(/\s+/u).some(token => token.startsWith(query))) return 400
  if (title.includes(query)) return 350
  if (path.split('/').some(segment => segment.startsWith(query))) return 300
  if (path.includes(query)) return 250
  if (vault.includes(query)) return 200
  return 0
}

export function rankKnowledgeCatalog(
  candidates: readonly KnowledgeCatalogCandidate[],
  query: string,
  limit: number,
): KnowledgeCatalogCandidate[] {
  const needle = normalized(query.trim())
  return candidates
    .map(candidate => ({ candidate, score: score(candidate, needle) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score
      || compareCodePoints(a.candidate.title, b.candidate.title)
      || compareCodePoints(a.candidate.relativePath, b.candidate.relativePath)
      || compareCodePoints(a.candidate.key, b.candidate.key))
    .slice(0, Math.max(0, limit))
    .map(item => item.candidate)
}

export function candidateToOpenTab(
  candidate: KnowledgeCatalogCandidate,
): OpenKnowledgeTab {
  return {
    vaultId: candidate.vaultId,
    noteId: candidate.noteId,
    title: candidate.title,
    relativePath: candidate.relativePath,
  }
}

export function searchResultToOpenTab(
  result: SearchResult,
): OpenKnowledgeTab | null {
  const provenance = result.vault_provenance
  const relativePath = canonicalVaultRelativePathSchema.safeParse(
    provenance?.relative_path,
  )
  if (
    !provenance
    || provenance.canonical_external !== true
    || !provenance.vault_id
    || !result.id
    || !relativePath.success
    || !/^[0-9a-f]{64}$/iu.test(provenance.source_hash)
  ) return null
  return {
    vaultId: provenance.vault_id,
    noteId: result.id,
    title: result.title.trim() || titleFromPath(relativePath.data),
    relativePath: relativePath.data,
  }
}
