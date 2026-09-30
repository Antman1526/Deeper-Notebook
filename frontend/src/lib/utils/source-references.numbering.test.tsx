import { describe, expect, it } from 'vitest'

import { convertReferencesToCompactMarkdown } from './source-references'

// The chat renderer numbers citation chips first, then hands the remaining
// reference shapes to this converter. It must be able to continue the numbering
// so two different sources never both read "1".

describe('convertReferencesToCompactMarkdown numbering', () => {
  it('starts at 1 by default', () => {
    const out = convertReferencesToCompactMarkdown('See source_insight:abc.', 'References')
    expect(out).toContain('[1](#ref-source_insight-abc)')
  })

  it('continues from a supplied first number, in the inline link and the reference list', () => {
    const out = convertReferencesToCompactMarkdown('See source_insight:abc and note:xyz.', 'References', 4)
    expect(out).toContain('[4](#ref-source_insight-abc)')
    expect(out).toContain('[5](#ref-note-xyz)')
    expect(out).toContain('[4] - [source_insight:abc]')
    expect(out).not.toContain('[1](')
  })
})
