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

  it('rejects embedded absolute paths in saved-search queries while preserving prose', () => {
    const base = {
      kind: 'saved_search',
      search_mode: 'text',
      space_ids: ['knowledge_engine_space:overlay'],
      authority_kinds: ['external_read_only'],
    }
    for (const query of [
      'Read /Users/Antman/Private.md before recording.',
      'Read C:\\Users\\Antman\\Private.md before recording.',
      'Read \\\\server\\share\\Private.md before recording.',
      'Read //server/share/Private.md before recording.',
      'Read file:///Users/Antman/Private.md before recording.',
    ]) {
      expect(() => fromPodcastSelectionWire({ ...base, query })).toThrow()
    }
    const prose = 'Compare pros/cons and/or 1/2 at https://example.com/guide.'
    expect(fromPodcastSelectionWire({ ...base, query: prose })).toEqual({
      kind: 'saved_search',
      query: prose,
      searchMode: 'text',
      spaceIds: ['knowledge_engine_space:overlay'],
      authorityKinds: ['external_read_only'],
    })
  })
})
