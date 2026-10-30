import { describe, expect, it } from 'vitest'

import { convertReferencesToCompactMarkdown, convertReferencesToMarkdownLinks } from './source-references'

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

  it('skips references inside inline code spans and fenced code blocks', () => {
    const input = 'Use `[source:inline_code]` or:\n```ts\nconst ref = "[source:fenced_code]"\n```\nReal citation [source:real_doc].'
    const out = convertReferencesToCompactMarkdown(input, 'References')
    expect(out).toContain('`[source:inline_code]`')
    expect(out).toContain('const ref = "[source:fenced_code]"')
    expect(out).toContain('[1](#ref-source-real_doc)')
    expect(out).not.toContain('#ref-source-inline_code')
    expect(out).not.toContain('#ref-source-fenced_code')
  })

  it('skips references inside unclosed streaming code fences across converters', () => {
    const streaming = 'Real [source:real_doc] and:\n```ts\nconst x = "[source:unclosed_fence]"'
    const compact = convertReferencesToCompactMarkdown(streaming, 'References')
    expect(compact).toContain('[1](#ref-source-real_doc)')
    expect(compact).not.toContain('#ref-source-unclosed_fence')
    const links = convertReferencesToMarkdownLinks(streaming)
    expect(links).toContain('#ref-source-real_doc')
    expect(links).not.toContain('#ref-source-unclosed_fence')
  })
})
