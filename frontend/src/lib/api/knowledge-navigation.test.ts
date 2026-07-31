import { describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import { parseBookmark } from './knowledge-navigation'

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
})
