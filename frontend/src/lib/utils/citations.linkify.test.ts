import { describe, expect, it } from 'vitest'
import { CITATION_HREF_PREFIX, linkifyCitations, parseCitationHref } from './citations'

// T0-5 — citations must stay inside the sentence they support. The old renderer
// split the answer on every marker and rendered each piece as its own block of
// markdown, which pushed every pill onto its own line. linkifyCitations turns
// markers into ordinary markdown links so ONE markdown pass keeps them inline.

describe('linkifyCitations', () => {
  it('returns the text untouched when there are no citations', () => {
    expect(linkifyCitations('Plain answer, nothing cited.')).toEqual({
      markdown: 'Plain answer, nothing cited.',
      citations: [],
    })
  })

  it('returns an empty result for empty input', () => {
    expect(linkifyCitations('')).toEqual({ markdown: '', citations: [] })
  })

  it('replaces a source marker with a numbered link that points back into the citation list', () => {
    const { markdown, citations } = linkifyCitations('See [source:abc123] for details.')
    expect(markdown).toBe(`See [1](${CITATION_HREF_PREFIX}0) for details.`)
    expect(citations).toEqual([
      { kind: 'source', value: 'abc123', number: 1, precedingText: 'See ' },
    ])
  })

  it('numbers distinct citations by first appearance and reuses the number for repeats', () => {
    const { markdown, citations } = linkifyCitations(
      'A [source:a]. B [note:n]. C [source:a]. D [insight:i].',
    )
    expect(citations.map(c => c.number)).toEqual([1, 2, 1, 3])
    expect(markdown).toBe(
      `A [1](${CITATION_HREF_PREFIX}0). B [2](${CITATION_HREF_PREFIX}1). `
      + `C [1](${CITATION_HREF_PREFIX}2). D [3](${CITATION_HREF_PREFIX}3).`,
    )
  })

  it('does not spend a number on MCP tool-call markers', () => {
    const { citations } = linkifyCitations('Ran a search [mcp:1] then read [source:a] and [mcp:2].')
    expect(citations.map(c => [c.kind, c.number])).toEqual([
      ['mcp', null],
      ['source', 1],
      ['mcp', null],
    ])
  })

  it('records the text since the previous marker as the citing context', () => {
    const { citations } = linkifyCitations('First claim. [source:a] Second claim. [source:b]')
    expect(citations.map(c => c.precedingText)).toEqual([
      'First claim. ',
      ' Second claim. ',
    ])
  })

  it('gives back-to-back markers an empty citing context', () => {
    const { citations } = linkifyCitations('Both agree [source:a][source:b]')
    expect(citations.map(c => c.precedingText)).toEqual(['Both agree ', ''])
  })

  it('leaves markers inside fenced code blocks and inline code literal', () => {
    const text = 'Use `[source:x]` inline.\n\n```\n[source:y]\n```\n\nBut cite [source:z].'
    const { markdown, citations } = linkifyCitations(text)
    expect(markdown).toContain('`[source:x]`')
    expect(markdown).toContain('```\n[source:y]\n```')
    expect(citations.map(c => c.value)).toEqual(['z'])
  })

  it('leaves markers alone inside a code fence that has not closed yet (streaming)', () => {
    const { markdown, citations } = linkifyCitations('Cite [source:a] first.\n```js\nconst x = "[source:b]"')
    expect(citations.map(c => c.value)).toEqual(['a'])
    expect(markdown).toContain('"[source:b]"')
  })

  it('does the same for an unclosed tilde fence', () => {
    const { citations } = linkifyCitations('Cite [source:a].\n~~~\n[source:b]')
    expect(citations.map(c => c.value)).toEqual(['a'])
  })

  it('is repeatable — module-level regex state does not leak between calls', () => {
    const text = 'One [source:a] two [note:b]'
    expect(linkifyCitations(text)).toEqual(linkifyCitations(text))
  })
})

describe('parseCitationHref', () => {
  it('returns the citation index for a citation href', () => {
    expect(parseCitationHref(`${CITATION_HREF_PREFIX}7`)).toBe(7)
  })

  it('returns null for ordinary and compact-reference links', () => {
    expect(parseCitationHref('https://example.com')).toBeNull()
    expect(parseCitationHref('#ref-source-abc')).toBeNull()
    expect(parseCitationHref(undefined)).toBeNull()
  })

  it('returns null for a malformed citation href', () => {
    expect(parseCitationHref(`${CITATION_HREF_PREFIX}x`)).toBeNull()
    expect(parseCitationHref(CITATION_HREF_PREFIX)).toBeNull()
  })
})
