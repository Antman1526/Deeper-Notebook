import { unified } from 'unified'
import remarkParse from 'remark-parse'
import { describe, expect, it } from 'vitest'

import { remarkVaultLinks } from './remark-vault-links'

function utf8ByteLength(value: string) {
  return new TextEncoder().encode(value).length
}

describe('remarkVaultLinks', () => {
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
})
