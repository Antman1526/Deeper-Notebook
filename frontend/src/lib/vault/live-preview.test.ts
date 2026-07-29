import { markdown, markdownLanguage } from '@codemirror/lang-markdown'
import { EditorState } from '@codemirror/state'
import { Decoration } from '@codemirror/view'
import { describe, expect, it, vi } from 'vitest'

import { buildLivePreviewDecorationRecords } from './live-preview'

function previewState(doc: string, anchor = doc.length) {
  return EditorState.create({
    doc,
    selection: { anchor },
    extensions: [markdown({ base: markdownLanguage })],
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
    ['inline code', '`[[Not]] $x$ [^x] ~~x~~ [ ]`', 'inline-code'],
    ['fenced code', '```md\n[[Not]] $x$ [^x] ~~x~~ [ ]\n```', 'fenced-code'],
  ] as const)('does not decorate scanner syntax inside %s', (_name, source, allowedKind) => {
    const state = previewState(source)
    const records = buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])

    const forbiddenKinds = new Set([
      'wiki-link',
      'tag',
      'footnote-mark',
      'math-mark',
      'strikethrough-mark',
      'task-marker',
    ])
    expect(records.filter((record) => forbiddenKinds.has(record.kind))).toEqual([])
    expect(records.some((record) => record.kind.startsWith(allowedKind))).toBe(true)
  })

  it('does not decorate a prose checkbox lookalike as a task', () => {
    const state = previewState('prose [ ]')

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }]))
      .toEqual([])
  })

  it('does not decorate a footnote parser artifact as a Markdown link', () => {
    const state = previewState('evidence[^1]\n\n[^1]: source')

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])
      .filter((record) => record.kind.startsWith('markdown-link')))
      .toEqual([])
  })

  it.each([
    ['tag', 'dn-live-preview-tag', ['footnote-mark', 'math-mark']],
    ['footnote', 'dn-live-preview-footnote', ['tag', 'math-mark']],
    ['math', 'dn-live-preview-math', ['tag', 'footnote-mark']],
  ] as const)('isolates a failed %s decoration from peer scanner constructs', (
    _name,
    failedClass,
    survivingKinds,
  ) => {
    const state = previewState('#tag $x$ [^1]')
    const originalMark = Decoration.mark
    const mark = vi.spyOn(Decoration, 'mark').mockImplementation((spec = {}) => {
      if (spec.class === failedClass) throw new Error('synthetic decoration failure')
      return originalMark(spec)
    })

    try {
      const records = buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])
      expect(records.some((record) => record.decoration.spec.class === failedClass)).toBe(false)
      expect(records.map((record) => record.kind))
        .toEqual(expect.arrayContaining([...survivingKinds]))
    } finally {
      mark.mockRestore()
    }
  })

  it('uses the state-managed syntax tree without a full parser parse', () => {
    const state = previewState('# Heading\n\n~~strike~~\n\n- [ ] task')
    const parse = vi.spyOn(markdownLanguage.parser, 'parse')

    try {
      buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])
      expect(parse).not.toHaveBeenCalled()
    } finally {
      parse.mockRestore()
    }
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

  it('collapses a Setext heading underline on its own line', () => {
    const state = previewState('Plan\n---')

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({ kind: 'heading-mark', from: 5, to: 8 }),
      ]))
  })

  it('collapses every marker in a multi-line blockquote', () => {
    const state = previewState('> one\n> two')

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])
      .filter((record) => record.kind === 'blockquote-mark'))
      .toEqual([
        expect.objectContaining({ from: 0, to: 2 }),
        expect.objectContaining({ from: 6, to: 8 }),
      ])
  })

  it.each([
    ['Setext heading', 'Plan\n---', 6, 'heading-mark'],
    ['multi-line blockquote', '> one\n> two', 7, 'blockquote-mark'],
  ] as const)('reveals all %s punctuation when selection intersects the construct', (
    _name,
    source,
    anchor,
    markerKind,
  ) => {
    const state = previewState(source, anchor)

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: state.doc.length }])
      .filter((record) => record.kind === markerKind))
      .toEqual([])
  })
})
