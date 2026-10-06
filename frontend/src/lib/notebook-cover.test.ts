import { describe, expect, it } from 'vitest'

import { NOTEBOOK_COVER_TONES, notebookCoverTone } from './notebook-cover'

// v0.8.130 — every notebook is bound in one of a few cloth colours. The colour comes
// from the notebook's id, so it never changes between visits and needs no storage.
describe('notebookCoverTone', () => {
  it('always gives a notebook the same cover', () => {
    expect(notebookCoverTone('notebook:abc')).toBe(notebookCoverTone('notebook:abc'))
  })

  it('only uses the bound cloth colours', () => {
    for (let index = 0; index < 200; index += 1) {
      expect(NOTEBOOK_COVER_TONES).toContain(notebookCoverTone(`notebook:${index}`))
    }
  })

  it('spreads notebooks across the colours', () => {
    const seen = new Set(Array.from({ length: 200 }, (_, index) => notebookCoverTone(`notebook:${index}`)))
    expect(seen.size).toBe(NOTEBOOK_COVER_TONES.length)
  })

  it('still binds a notebook with an empty id', () => {
    expect(NOTEBOOK_COVER_TONES).toContain(notebookCoverTone(''))
  })
})
