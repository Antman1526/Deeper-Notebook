import { markdown } from '@codemirror/lang-markdown'
import { EditorState } from '@codemirror/state'
import { describe, expect, it } from 'vitest'

import { buildLivePreviewDecorationRecords } from './live-preview'

function previewState(doc: string, anchor = doc.length) {
  return EditorState.create({
    doc,
    selection: { anchor },
    extensions: [markdown()],
  })
}

describe('buildLivePreviewDecorationRecords', () => {
  it('collapses supported punctuation outside the selection', () => {
    const state = previewState('# Plan\n\n**Strong** and `code`', 7)

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({ kind: 'heading-mark', from: 0, to: 2 }),
        expect.objectContaining({ kind: 'strong-mark', from: 8, to: 10 }),
        expect.objectContaining({ kind: 'inline-code-mark' }),
      ]))
  })

  it('reveals exact tokens intersecting the selection', () => {
    const state = previewState('**Strong**', 1)

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }]))
      .toEqual([])
  })

  it('leaves unsupported source syntax visible', () => {
    const state = previewState('%% Obsidian comment syntax remains inspectable %%')

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }]))
      .toEqual([])
  })

  it.each([
    ['heading', '# Heading', 'heading-mark'],
    ['emphasis', '*emphasis*', 'emphasis-mark'],
    ['strong', '**strong**', 'strong-mark'],
    ['strikethrough', '~~strike~~', 'strikethrough-mark'],
    ['inline code', '`code`', 'inline-code-mark'],
    ['fenced code', '```ts\nconst x = 1\n```', 'fenced-code-mark'],
    ['Markdown link', '[Page](pages/page.md)', 'markdown-link'],
    ['wiki link', '[[Page]]', 'wiki-link'],
    ['task marker', '- [ ] task', 'task-marker'],
    ['blockquote', '> quote', 'blockquote-mark'],
    ['horizontal rule', '---', 'horizontal-rule'],
    ['ordered list', '1. item', 'ordered-list-mark'],
    ['unordered list', '- item', 'unordered-list-mark'],
    ['tag', '#research', 'tag'],
    ['footnote', 'evidence[^1]\n\n[^1]: source', 'footnote-mark'],
    ['math', '$x^2$', 'math-mark'],
  ] as const)('decorates %s', (_name, source, expectedKind) => {
    const state = previewState(source)
    const records = buildLivePreviewDecorationRecords(
      state,
      [{ from: 0, to: state.doc.length }],
    )

    expect(records).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: expectedKind }),
    ]))
  })

  it('only decorates constructs intersecting a visible range', () => {
    const state = previewState('**outside**\n\n**inside**')
    const inside = state.doc.toString().indexOf('**inside**')

    const records = buildLivePreviewDecorationRecords(state, [{
      from: inside,
      to: state.doc.length,
    }])

    expect(records).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'strong-mark', from: inside, to: inside + 2 }),
    ]))
    expect(records.some((record) => record.from < inside)).toBe(false)
  })

  it('does not make cross-line punctuation replacements', () => {
    const state = previewState('```ts\nconst x = 1\n```')

    const records = buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])

    expect(records).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'fenced-code-mark' }),
    ]))
    expect(records.filter((record) => record.kind === 'fenced-code-mark').every((record) => {
      const fromLine = state.doc.lineAt(record.from).number
      const toLine = state.doc.lineAt(Math.max(record.from, record.to - 1)).number
      return fromLine === toLine
    })).toBe(true)
  })
})
