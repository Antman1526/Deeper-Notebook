import { describe, expect, it } from 'vitest'

import {
  fromPodcastSelectionWire,
  normalizePodcastSelections,
  podcastSelectionSchema,
  toPodcastSelectionWire,
} from './selection'

describe('podcast selection contracts', () => {
  it('rejects a filesystem path and unknown fields at the browser boundary', () => {
    expect(() => podcastSelectionSchema.parse({
      kind: 'knowledge_document',
      documentId: '/Users/Antman/private.md',
    })).toThrow()
    expect(() => podcastSelectionSchema.parse({
      kind: 'knowledge_document',
      documentId: 'knowledge_engine_document:research',
      rootPath: '/Users/Antman/private',
    })).toThrow()
  })

  it('sorts and deduplicates graph references without mutating the caller input', () => {
    const selections = [{
      kind: 'graph_selection' as const,
      documentIds: [
        'knowledge_engine_document:zeta',
        'knowledge_engine_document:alpha',
        'knowledge_engine_document:zeta',
      ],
    }]

    expect(normalizePodcastSelections(selections)).toEqual([{
      kind: 'graph_selection',
      documentIds: [
        'knowledge_engine_document:alpha',
        'knowledge_engine_document:zeta',
      ],
    }])
    expect(selections[0].documentIds).toHaveLength(3)
  })

  it('maps a revision-bound knowledge reference to the strict API wire shape', () => {
    expect(toPodcastSelectionWire({
      kind: 'knowledge_document',
      documentId: 'knowledge_engine_document:research',
      expectedRevisionId: 'knowledge_engine_revision:one',
    })).toEqual({
      kind: 'knowledge_document',
      document_id: 'knowledge_engine_document:research',
      expected_revision_id: 'knowledge_engine_revision:one',
    })
  })

  it('converts a retry preview wire reference through the strict client union', () => {
    expect(fromPodcastSelectionWire({
      kind: 'knowledge_document',
      document_id: 'knowledge_engine_document:research',
      expected_revision_id: null,
    })).toEqual({
      kind: 'knowledge_document',
      documentId: 'knowledge_engine_document:research',
      expectedRevisionId: null,
    })
  })

  it('rejects unsafe or extra retry preview wire fields', () => {
    expect(() => fromPodcastSelectionWire({
      kind: 'knowledge_document',
      document_id: 'knowledge_engine_document:research',
      expected_revision_id: null,
      source_body: 'private body',
    })).toThrow()
  })
})
