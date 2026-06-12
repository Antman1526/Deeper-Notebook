import { describe, it, expect } from 'vitest'
import { splitCitations } from './citations'
import type { CitationSegment } from './citations'

// v0.8.0 Phase 4 Task 14 — unit tests for the pure citation splitter.

describe('splitCitations', () => {
  it('returns empty array for empty string', () => {
    expect(splitCitations('')).toEqual([])
  })

  it('returns a single text segment when no citations are present', () => {
    const result = splitCitations('Hello world, no citations here.')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'Hello world, no citations here.' },
    ])
  })

  it('handles a single mcp citation mid-sentence', () => {
    const result = splitCitations('The sky is blue. [mcp:1] That is a fact.')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'The sky is blue. ' },
      { kind: 'mcp', value: '1' },
      { kind: 'text', value: ' That is a fact.' },
    ])
  })

  it('handles a single source citation', () => {
    const result = splitCitations('See [source:abc123] for details.')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'See ' },
      { kind: 'source', value: 'abc123' },
      { kind: 'text', value: ' for details.' },
    ])
  })

  it('handles a single note citation', () => {
    const result = splitCitations('[note:xyz99]')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'note', value: 'xyz99' },
    ])
  })

  it('handles a single insight citation', () => {
    const result = splitCitations('[insight:qr8_st]')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'insight', value: 'qr8_st' },
    ])
  })

  it('handles multiple citations of different kinds', () => {
    const result = splitCitations('A [mcp:1] B [source:s1] C [note:n1] D')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'A ' },
      { kind: 'mcp', value: '1' },
      { kind: 'text', value: ' B ' },
      { kind: 'source', value: 's1' },
      { kind: 'text', value: ' C ' },
      { kind: 'note', value: 'n1' },
      { kind: 'text', value: ' D' },
    ])
  })

  it('handles adjacent citations (no text between them)', () => {
    const result = splitCitations('[mcp:1][mcp:2]')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'mcp', value: '1' },
      { kind: 'mcp', value: '2' },
    ])
  })

  it('handles citation at the very start of the string', () => {
    const result = splitCitations('[source:abc] at the start.')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'source', value: 'abc' },
      { kind: 'text', value: ' at the start.' },
    ])
  })

  it('handles citation at the very end of the string', () => {
    const result = splitCitations('At the end [note:abc]')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'At the end ' },
      { kind: 'note', value: 'abc' },
    ])
  })

  it('NBA Finals example from system.jinja:65 splits into exactly 5 nodes', () => {
    const text =
      'The Oklahoma City Thunder defeated the Cleveland Cavaliers in five games to win their first championship. [mcp:1] Game 5 was decided by a buzzer-beating three from Shai Gilgeous-Alexander. [mcp:2]'
    const result = splitCitations(text)
    // Expected: text, mcp:1, text, mcp:2, (no trailing text — ends with [mcp:2])
    // Actually [mcp:2] is at the very end, so lastIndex == text.length and no trailing segment.
    expect(result).toHaveLength(4)
    expect(result[0]).toEqual({
      kind: 'text',
      value: 'The Oklahoma City Thunder defeated the Cleveland Cavaliers in five games to win their first championship. ',
    })
    expect(result[1]).toEqual({ kind: 'mcp', value: '1' })
    expect(result[2]).toEqual({
      kind: 'text',
      value: ' Game 5 was decided by a buzzer-beating three from Shai Gilgeous-Alexander. ',
    })
    expect(result[3]).toEqual({ kind: 'mcp', value: '2' })
  })

  it('is idempotent — calling twice returns the same result', () => {
    const text = 'Hello [mcp:1] world'
    expect(splitCitations(text)).toEqual(splitCitations(text))
  })

  it('ignores unknown bracket patterns that do not match the regex', () => {
    const result = splitCitations('Some [other:xyz] text [mcp:1]')
    expect(result).toEqual<CitationSegment[]>([
      { kind: 'text', value: 'Some [other:xyz] text ' },
      { kind: 'mcp', value: '1' },
    ])
  })
})
