import { describe, expect, it, vi } from 'vitest'

import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import type { OverlayNote } from '@/lib/api/overlay'
import type { VaultFile, VaultMount } from '@/lib/api/vault'
import type { SearchResult } from '@/lib/types/search'
import {
  buildKnowledgeCatalog,
  candidateToOpenTab,
  rankKnowledgeCatalog,
  searchResultToOpenTab,
} from './knowledge-command-catalog'

const mounts: VaultMount[] = [
  {
    id: 'vault:research',
    name: 'Research Core',
    format_mode: 'obsidian',
    state: 'ready-read-only',
    watch_enabled: false,
  },
]

const file = (noteId: string, relativePath: string): VaultFile => ({
  id: `vault_file:${noteId}`,
  note_id: noteId,
  vault_id: 'vault:research',
  relative_path: relativePath,
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  parse_status: 'parsed',
  size_bytes: 10,
  modified_ns: 1,
  encoding: 'utf-8',
  newline: 'lf',
  deleted_state: 'present',
})

describe('knowledge command catalog', () => {
  it('keeps overlay and external candidates distinct when IDs or titles match', () => {
    const overlay: OverlayNote = {
      id: 'note:shared', source_authority: 'overlay', space_id: 'overlay_space:default',
      projected_note_id: 'projected:shared', stable_id: 'a'.repeat(20), kind: 'unique', date_key: null,
      relative_path: 'Notes/Shared.md', title: 'Shared', content_hash: 'a'.repeat(64), revision: 1,
      projection_state: 'current', encoding: 'utf-8', newline: 'lf',
      created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
    }
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [file('note:shared', 'Shared.md')]]]),
      [],
      [overlay],
    )

    expect(rankKnowledgeCatalog(catalog, 'shared', 10)).toHaveLength(2)
    expect(rankKnowledgeCatalog(catalog, 'shared', 10).map(candidate => candidate.sourceAuthority))
      .toEqual(['overlay', 'external-vault'])
    expect(candidateToOpenTab(catalog.find(candidate => candidate.sourceAuthority === 'overlay')!))
      .toMatchObject({ sourceAuthority: 'overlay', vaultId: 'overlay_space:default' })
  })
  it('ranks exact titles before prefixes, path matches, and vault matches', () => {
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([
        ['vault:research', [
          file('note:exact', 'Research.md'),
          file('note:prefix', 'Research Methods.md'),
          file('note:path', 'research/Evidence.md'),
        ]],
      ]),
      [],
    )

    expect(rankKnowledgeCatalog(catalog, 'research', 10).map(item => item.noteId))
      .toEqual(['note:exact', 'note:prefix', 'note:path'])
  })

  it('folds case and diacritics and marks already-open notes', () => {
    const openTabs: OpenKnowledgeTab[] = [{
      vaultId: 'vault:research',
      noteId: 'note:cafe',
      title: 'Café',
      relativePath: 'Café.md',
    }]
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [file('note:cafe', 'Café.md')]]]),
      openTabs,
    )

    expect(rankKnowledgeCatalog(catalog, 'cafe', 10)[0]).toMatchObject({
      noteId: 'note:cafe',
      isOpen: true,
    })
  })

  it('matches Turkish dotted and dotless capital I without ambient locale rules', () => {
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [
        file('note:dotted', 'İstanbul.md'),
        file('note:capital', 'INDEX.md'),
      ]]]),
      [],
    )

    expect(rankKnowledgeCatalog(catalog, 'istanbul', 10).map(item => item.noteId))
      .toEqual(['note:dotted'])
    expect(rankKnowledgeCatalog(catalog, 'index', 10).map(item => item.noteId))
      .toEqual(['note:capital'])
  })

  it('uses deterministic code-point tie ordering without locale-sensitive methods', () => {
    const localeLower = vi.spyOn(String.prototype, 'toLocaleLowerCase')
      .mockImplementation(() => { throw new Error('ambient locale lowercasing used') })
    const localeCompare = vi.spyOn(String.prototype, 'localeCompare')
      .mockImplementation(() => { throw new Error('ambient locale comparison used') })
    try {
      const catalog = buildKnowledgeCatalog(
        mounts,
        new Map([['vault:research', [
          file('note:z', 'Zulu.md'),
          file('note:a', 'Alpha.md'),
          file('note:accent', 'Álpha.md'),
        ]]]),
        [],
      )

      expect(rankKnowledgeCatalog(catalog, '', 10).map(item => item.noteId))
        .toEqual(['note:a', 'note:z', 'note:accent'])
    } finally {
      localeLower.mockRestore()
      localeCompare.mockRestore()
    }
  })

  it('maps a candidate to a canonical workspace tab request', () => {
    const [candidate] = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [file('note:plan', 'Plan.md')]]]),
      [],
    )

    expect(candidateToOpenTab(candidate)).toEqual({
      sourceAuthority: 'external-vault',
      vaultId: 'vault:research',
      noteId: 'note:plan',
      title: 'Plan',
      relativePath: 'Plan.md',
    })
  })

  it('accepts only complete canonical search provenance', () => {
    const result = {
      id: 'note:plan',
      title: 'Plan',
      parent_id: 'vault:research',
      final_score: 1,
      created: '',
      updated: '',
      vault_provenance: {
        canonical_external: true,
        vault_id: 'vault:research',
        relative_path: 'Plan.md',
        source_hash: 'b'.repeat(64),
      },
    } satisfies SearchResult

    expect(searchResultToOpenTab(result)).toEqual({
      vaultId: 'vault:research',
      noteId: 'note:plan',
      title: 'Plan',
      relativePath: 'Plan.md',
    })
    expect(searchResultToOpenTab({
      ...result,
      vault_provenance: {
        ...result.vault_provenance,
        relative_path: '/Users/owner/Plan.md',
      },
    })).toBeNull()
    expect(searchResultToOpenTab({
      ...result,
      vault_provenance: {
        ...result.vault_provenance,
        source_hash: 'not-a-hash',
      },
    })).toBeNull()
  })
})
