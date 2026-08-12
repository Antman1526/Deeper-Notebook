import { describe, expect, it } from 'vitest'

import { decodeAnkiImportPreview } from './study-anki'

describe('Study Anki decoders', () => {
  it('rejects missing collection identity and unknown fields', () => {
    expect(() => decodeAnkiImportPreview({
      schema_version: 1,
      job_id: 'anki_job:' + 'a'.repeat(32),
      status: 'preview_ready',
      card_count: 1,
      transformed_count: 0,
      skipped_count: 0,
      rejected_count: 0,
      package_sha256: 'a'.repeat(64),
      unexpected: true,
    })).toThrow('Invalid Study Anki response')
  })

  it('accepts the strict preview contract', () => {
    expect(decodeAnkiImportPreview({
      schema_version: 1,
      job_id: 'anki_job:' + 'a'.repeat(32),
      status: 'preview_ready',
      card_count: 1,
      transformed_count: 0,
      skipped_count: 0,
      rejected_count: 0,
      package_sha256: 'a'.repeat(64),
      collection_member: 'collection.anki2',
    }).collection_member).toBe('collection.anki2')
  })
})
