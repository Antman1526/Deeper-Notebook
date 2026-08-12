import { describe, expect, it } from 'vitest'

import { decodeStudyMasteryProjection } from './study-progress'

describe('study progress wire decoder', () => {
  it('keeps valid versioned projection data', () => {
    expect(decodeStudyMasteryProjection({
      schema_version: 1,
      concepts: [],
      review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0 },
      proposals: [],
      generated_at: '2026-08-12T12:00:00Z',
      memory_writes: [],
    }).schema_version).toBe(1)
  })

  it.each([
    { memory_writes: ['unexpected'] },
    { generated_at: '2026-08-12T12:00:00' },
    { review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0, extra: true } },
  ])('rejects malformed projection boundary %#', (patch) => {
    expect(() => decodeStudyMasteryProjection({
      schema_version: 1,
      concepts: [],
      review_consistency: { reviews: 0, lapses: 0, due_reviews: 0, on_time_rate: 0 },
      proposals: [],
      generated_at: '2026-08-12T12:00:00Z',
      memory_writes: [],
      ...patch,
    })).toThrow('Invalid Study progress response')
  })
})
