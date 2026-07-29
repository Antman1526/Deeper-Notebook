import { unified } from 'unified'
import remarkParse from 'remark-parse'
import { describe, expect, it, vi } from 'vitest'

import { buildUniqueResolvedSpanMap, remarkVaultLinks } from './remark-vault-links'

function utf8ByteLength(value: string) {
  return new TextEncoder().encode(value).length
}

describe('remarkVaultLinks', () => {
  const canonicalLink = {
    id: 'canonical',
    source_note_id: 'note:plan',
    target_note_id: 'note:research',
    target_note_title: 'Research',
    target_relative_path: 'research.md',
    target_text: 'Research',
    link_kind: 'wikilink',
    resolved: true,
    source_start: 2,
    source_end: 14,
  }

  it.each([
    ['a resolved and unresolved record', [canonicalLink, { ...canonicalLink, id: 'unresolved', resolved: false, target_note_id: null }]],
    ['duplicate records for the same target', [canonicalLink, { ...canonicalLink, id: 'duplicate' }]],
    ['a noncanonical resolved record', [{ ...canonicalLink, target_note_title: null }]],
  ])('does not map %s sharing one source span', (_label, links) => {
    expect(buildUniqueResolvedSpanMap(links)).toEqual(new Map())
  })

  it('accepts an empty but present canonical target title', () => {
    const link = { ...canonicalLink, target_note_title: '' }

    expect(buildUniqueResolvedSpanMap([link]).get('2:14')).toBe(link)
  })

  it('preserves source text and resolves duplicate labels only by their UTF-8 spans', () => {
    const markdown = 'é [[Research|Same]] then [[Research|Same]]'
    const firstStart = utf8ByteLength('é ')
    const firstEnd = firstStart + utf8ByteLength('[[Research|Same]]')
    const secondStart = utf8ByteLength('é [[Research|Same]] then ')
    const secondEnd = secondStart + utf8ByteLength('[[Research|Same]]')
    const file = { value: markdown }
    const tree = unified().use(remarkParse).parse(file)
    const links = [
      { id: 'one', source_note_id: 'note:plan', target_note_id: 'note:first', target_note_title: 'First', target_relative_path: 'first.md', target_text: 'Research', link_kind: 'wikilink', resolved: true, source_start: firstStart, source_end: firstEnd },
      { id: 'two', source_note_id: 'note:plan', target_note_id: 'note:second', target_note_title: 'Second', target_relative_path: 'second.md', target_text: 'Research', link_kind: 'wikilink', resolved: true, source_start: secondStart, source_end: secondEnd },
    ]

    const transformer = remarkVaultLinks({ links })
    transformer(tree, file)

    expect(file.value).toBe(markdown)
    const paragraph = tree.children[0] as unknown as { children: Array<Record<string, unknown>> }
    const anchors = paragraph.children.filter((child) => child.type === 'link')
    expect(anchors).toHaveLength(2)
    expect(anchors.map((anchor) => anchor.position)).toEqual([
      { start: { line: 1, column: 3, offset: 2 }, end: { line: 1, column: 20, offset: 19 } },
      { start: { line: 1, column: 26, offset: 25 }, end: { line: 1, column: 43, offset: 42 } },
    ])
    expect(anchors.map((anchor) => (anchor.data as { hProperties: Record<string, number> }).hProperties)).toEqual([
      expect.objectContaining({ 'data-source-start': firstStart, 'data-source-end': firstEnd }),
      expect.objectContaining({ 'data-source-start': secondStart, 'data-source-end': secondEnd }),
    ])
  })

  it('does not transform wiki syntax nested inside a reference link', () => {
    const markdown = '[before [[Research]]][ref]\n\n[ref]: /target'
    const file = { value: markdown }
    const tree = unified().use(remarkParse).parse(file)

    remarkVaultLinks({ links: [] })(tree, file)

    expect(file.value).toBe(markdown)
    const paragraph = tree.children[0] as unknown as { children: Array<{ type: string; children?: Array<{ type: string }> }> }
    expect(paragraph.children[0].type).toBe('linkReference')
    expect(paragraph.children[0].children?.some((child) => child.type === 'link')).toBe(false)
  })

  it('positions a surrogate-pair alias at its visible source text', () => {
    const markdown = '😀 [[Research|Alias😀]]'
    const file = { value: markdown }
    const tree = unified().use(remarkParse).parse(file)

    remarkVaultLinks({ links: [] })(tree, file)

    const paragraph = tree.children[0] as unknown as { children: Array<Record<string, unknown>> }
    const anchor = paragraph.children.find((child) => child.type === 'link') as { children: Array<{ position: unknown }> }
    const aliasStart = markdown.indexOf('Alias')
    const aliasEnd = aliasStart + 'Alias😀'.length
    expect(anchor.children[0].position).toEqual({
      start: { line: 1, column: aliasStart + 1, offset: aliasStart },
      end: { line: 1, column: aliasEnd + 1, offset: aliasEnd },
    })
  })

  it('positions a trimmed alias correctly after CRLF', () => {
    const markdown = 'head\r\n[[Research|  Alias  ]]'
    const file = { value: markdown }
    const tree = unified().use(remarkParse).parse(file)

    remarkVaultLinks({ links: [] })(tree, file)

    const paragraph = tree.children[0] as unknown as { children: Array<Record<string, unknown>> }
    const anchor = paragraph.children.find((child) => child.type === 'link') as { children: Array<{ position: unknown }> }
    const aliasStart = markdown.indexOf('Alias')
    expect(anchor.children[0].position).toEqual({
      start: { line: 2, column: 14, offset: aliasStart },
      end: { line: 2, column: 19, offset: aliasStart + 5 },
    })
  })

  it('builds UTF-8 spans with linear encoding work for many wiki links', () => {
    const markdown = Array.from({ length: 200 }, (_, index) => `[[Note-${index}|Alias-${index}]]`).join(' ')
    const file = { value: markdown }
    const tree = unified().use(remarkParse).parse(file)
    const originalEncode = TextEncoder.prototype.encode
    let encodedCodeUnits = 0
    const encode = vi.spyOn(TextEncoder.prototype, 'encode').mockImplementation(function (this: TextEncoder, input = '') {
      encodedCodeUnits += input.length
      return originalEncode.call(this, input)
    })

    try {
      remarkVaultLinks({ links: [] })(tree, file)
      expect(encodedCodeUnits).toBeLessThan(markdown.length * 4)
    } finally {
      encode.mockRestore()
    }
  })
})
