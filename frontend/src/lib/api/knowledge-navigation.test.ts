import { describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import apiClient from './client'
import { knowledgeNavigationApi, parseBookmark } from './knowledge-navigation'

const plainBookmark = {
  schema_version: 1, id: 'knowledge_bookmark:one', target_kind: 'document',
  target: { kind: 'document', document_id: 'knowledge_engine_document:one' },
  display_label: 'One', authority_kind: null, space_id: null, tags: [], folder_id: null,
  position: 0, revision: 1, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}

describe('knowledge navigation API contracts', () => {
  it('rejects absolute paths and unknown target fields', () => {
    expect(() => parseBookmark({
      schema_version: 1,
      id: 'knowledge_bookmark:one',
      target_kind: 'document',
      target: {
        kind: 'document',
        document_id: 'knowledge_engine_document:one',
        root_path: '/Users/Antman/private',
      },
      display_label: 'One', target_state: 'available', target_document: null,
      authority_kind: null, space_id: null, tags: [], folder_id: null,
      position: 0, revision: 1, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })).toThrow()
  })

  it('parses the plain POST bookmark response without hydrated fields', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: plainBookmark } as never)

    await expect(knowledgeNavigationApi.createBookmark({
      operationId: 'operation:one', target: { kind: 'document', documentId: 'knowledge_engine_document:one' },
      displayLabel: 'One', authorityKind: null, spaceId: null, folderId: null, tags: [], position: 0,
    })).resolves.toMatchObject({ id: 'knowledge_bookmark:one', displayLabel: 'One' })
  })

  it('uses the backend singular repeated bookmark filter parameters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [], next_cursor: null } } as never)
    await knowledgeNavigationApi.listBookmarks({
      cursor: 'opaque', limit: 20, tags: ['Evidence'], targetKinds: ['document'],
      spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'],
    })
    expect(apiClient.get).toHaveBeenCalledWith('/deeper-notebook/knowledge/bookmarks', {
      params: {
        cursor: 'opaque', limit: 20, tag: ['Evidence'], target_kind: ['document'],
        space_id: ['knowledge_engine_space:research'], authority_kind: ['external_read_only'],
      },
    })
  })

  it('serializes a strict PATCH bookmark command', async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: plainBookmark } as never)
    await knowledgeNavigationApi.updateBookmark('knowledge_bookmark:one', {
      operationId: 'operation:two', expectedRevision: 1, displayLabel: 'Renamed',
    })
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/deeper-notebook/knowledge/bookmarks/knowledge_bookmark%3Aone',
      { operation_id: 'operation:two', expected_revision: 1, display_label: 'Renamed' },
    )
    await expect(knowledgeNavigationApi.updateBookmark('knowledge_bookmark:one', {
      operationId: 'operation:two', expectedRevision: 1, extra: true,
    } as never)).rejects.toThrow()
  })
})
