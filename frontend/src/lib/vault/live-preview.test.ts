import { markdown, markdownLanguage } from '@codemirror/lang-markdown'
import { Compartment, type Extension, EditorSelection, EditorState } from '@codemirror/state'
import {
  Decoration,
  type DecorationSet,
  EditorView,
  type ViewPlugin,
} from '@codemirror/view'
import { describe, expect, it, vi } from 'vitest'

import {
  buildLivePreviewDecorationRecords,
  livePreviewExtension,
} from './live-preview'

function previewState(doc: string, anchor = doc.length) {
  return EditorState.create({
    doc,
    selection: { anchor },
    extensions: [markdown({ base: markdownLanguage })],
  })
}

type PreviewPlugin = {
  decorations: DecorationSet
  update(update: {
    docChanged: boolean
    selectionSet: boolean
    viewportChanged: boolean
    view: EditorView
  }): void
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

  it('clips a long inline-math mark to a viewport in its middle', () => {
    const source = `$${'x'.repeat(6_000)}$`
    const state = previewState(source)
    const visible = { from: 3_000, to: 3_002 }

    const math = buildLivePreviewDecorationRecords(state, [visible])
      .filter((record) => record.kind === 'math-mark')

    expect(math).toEqual([
      expect.objectContaining({
        from: visible.from,
        to: visible.to,
      }),
    ])
    expect(math.every((record) =>
      record.from >= visible.from && record.to <= visible.to,
    )).toBe(true)
  })

  it('clips a long inline-math mark to its visible opening delimiter', () => {
    const source = `$${'x'.repeat(6_000)}$`
    const state = previewState(source)

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: 1 }]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          kind: 'math-mark',
          from: 0,
          to: 1,
        }),
      ]))
  })

  it('clips a long inline-math mark to its visible closing delimiter', () => {
    const source = `$${'x'.repeat(6_000)}$`
    const state = previewState(source)
    const visible = { from: source.length - 1, to: source.length }

    expect(buildLivePreviewDecorationRecords(state, [visible]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          kind: 'math-mark',
          from: visible.from,
          to: visible.to,
        }),
      ]))
  })

  it.each([
    ['inline code', (math: string) => `\`${math}\``],
    ['Markdown link', (math: string) => `[${math}](page.md)`],
  ] as const)('excludes long inline math inside %s', (_name, wrap) => {
    const math = `$${'x'.repeat(6_000)}$`
    const source = wrap(math)
    const middle = source.indexOf('x') + 3_000
    const state = previewState(source)

    expect(buildLivePreviewDecorationRecords(
      state,
      [{ from: middle, to: middle + 2 }],
    ).filter((record) => record.kind === 'math-mark')).toEqual([])
  })

  it('reuses its math interval index for viewport rebuilds', () => {
    const source = `$${'x'.repeat(6_000)}$`
    const visible = { from: 3_000, to: 3_002 }
    const extension = livePreviewExtension({})
    const [pluginExtension] = extension as readonly Extension[]
    const plugin = pluginExtension as ViewPlugin<PreviewPlugin>
    const view = new EditorView({
      state: EditorState.create({
        doc: source,
        selection: { anchor: source.length },
        extensions: [
          markdown({ base: markdownLanguage }),
          extension,
        ],
      }),
    })
    const instance = view.plugin(plugin)!
    const toString = vi.spyOn(view.state.doc, 'toString')
    const sliceString = vi.spyOn(view.state.doc, 'sliceString')
    const viewportView = new Proxy(view, {
      get(target, property) {
        if (property === 'visibleRanges') return [visible]
        return Reflect.get(target, property, target)
      },
    })

    try {
      instance.update({
        docChanged: false,
        selectionSet: false,
        viewportChanged: true,
        view: viewportView,
      })

      const math: Array<{ from: number; to: number }> = []
      instance.decorations.between(visible.from, visible.to, (from, to, decoration) => {
        if (decoration.spec.class === 'dn-live-preview-math') math.push({ from, to })
      })
      expect(math).toEqual([visible])
      expect(toString).not.toHaveBeenCalled()
      expect(sliceString.mock.calls.every(([from = 0, to = view.state.doc.length]) =>
        to - from <= 4_106,
      )).toBe(true)
    } finally {
      view.destroy()
    }
  })

  it('clips a long fenced-code construct to a tiny visible range', () => {
    const source = `\`\`\`text\n${'x'.repeat(20_000)}\n\`\`\``
    const state = previewState(source)
    const visible = { from: 10_000, to: 10_002 }
    buildLivePreviewDecorationRecords(state, [visible])
    const sliceString = vi.spyOn(state.doc, 'sliceString')

    const records = buildLivePreviewDecorationRecords(state, [visible])

    expect(records).not.toEqual([])
    expect(records.every((record) =>
      record.from >= visible.from
      && record.to <= visible.to
      && record.to - record.from <= visible.to - visible.from,
    )).toBe(true)
    const readLengths = sliceString.mock.calls.map(([from = 0, to = state.doc.length]) =>
      to - from,
    )
    expect(readLengths.filter((length) => length === 4_106).length)
      .toBeGreaterThanOrEqual(3)
  })

  it('collapses a visible opening fence on a long fenced-code construct', () => {
    const source = `\`\`\`text\n${'x'.repeat(20_002)}\n\`\`\``
    const state = previewState(source)
    const visible = { from: 0, to: 3 }

    expect(buildLivePreviewDecorationRecords(state, [visible]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          kind: 'fenced-code-mark',
          from: 0,
          to: 3,
        }),
      ]))
  })

  it('collapses a visible closing fence on a long fenced-code construct', () => {
    const source = `\`\`\`text\n${'x'.repeat(20_002)}\n\`\`\``
    const state = previewState(source)
    const visible = { from: source.length - 3, to: source.length }

    expect(buildLivePreviewDecorationRecords(state, [visible]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          kind: 'fenced-code-mark',
          from: source.length - 3,
          to: source.length,
        }),
      ]))
  })

  it('collapses a visible marker on a long blockquote with bounded reads', () => {
    const prefix = 'intro\n\n'
    const source = `${prefix}> ${'x'.repeat(7_000)}\n\ntail`
    const state = previewState(source)
    const visible = { from: prefix.length, to: prefix.length + 2 }
    buildLivePreviewDecorationRecords(state, [visible])
    const sliceString = vi.spyOn(state.doc, 'sliceString')

    const records = buildLivePreviewDecorationRecords(state, [visible])

    expect(records).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: 'blockquote-mark',
        from: prefix.length,
        to: prefix.length + 2,
      }),
    ]))
    const fragmentReadLengths = sliceString.mock.calls
      .filter(([from = 0, to = state.doc.length]) =>
        from !== 0 || to !== state.doc.length,
      )
      .map(([from = 0, to = state.doc.length]) => to - from)
    expect(fragmentReadLengths).not.toEqual([])
    expect(Math.max(...fragmentReadLengths)).toBeLessThanOrEqual(4_106)
  })

  it('collapses a visible paired marker on a long inline construct', () => {
    const source = `**${'x'.repeat(5_000)}**`
    const state = previewState(source)

    expect(buildLivePreviewDecorationRecords(state, [{ from: 0, to: 2 }]))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          kind: 'strong-mark',
          from: 0,
          to: 2,
        }),
      ]))
  })

  it('reuses its document source-index cache for viewport-driven decoration rebuilds', () => {
    const extension = livePreviewExtension({})
    const [pluginExtension] = extension as readonly Extension[]
    const plugin = pluginExtension as ViewPlugin<PreviewPlugin>
    const view = new EditorView({
      state: EditorState.create({
        doc: `${'# Plan\n\n'.repeat(2_000)}[[Research]]`,
        extensions: [
          markdown({ base: markdownLanguage }),
          extension,
        ],
      }),
    })
    const toString = vi.spyOn(view.state.doc, 'toString')

    try {
      view.plugin(plugin)!.update({
        docChanged: false,
        selectionSet: false,
        viewportChanged: true,
        view,
      })

      expect(toString).not.toHaveBeenCalled()
    } finally {
      view.destroy()
    }
  })

  it('rebuilds its source cache for changed raw line endings on the same document', () => {
    const lfSource = 'intro\n[[Research]]'
    const crlfSource = 'intro\r\n[[Research]]'
    const onNavigate = vi.fn()
    const linkFor = (source: string) => ({
      id: 'link:research',
      source_note_id: 'note:plan',
      target_note_id: 'note:research',
      target_note_title: 'Research',
      target_relative_path: 'pages/research.md',
      target_text: 'Research',
      link_kind: 'wikilink',
      resolved: true,
      source_start: new TextEncoder().encode(source.slice(0, source.indexOf('[['))).length,
      source_end: new TextEncoder().encode(source).length,
    })
    const compartment = new Compartment()
    const view = new EditorView({
      state: EditorState.create({
        doc: lfSource,
        extensions: [
          markdown({ base: markdownLanguage }),
          compartment.of(livePreviewExtension({
            links: [linkFor(lfSource)],
            onNavigate,
            source: lfSource,
          })),
        ],
      }),
    })
    const document = view.state.doc
    const toString = vi.spyOn(document, 'toString')

    try {
      view.dispatch({
        effects: compartment.reconfigure(livePreviewExtension({
          links: [linkFor(crlfSource)],
          onNavigate,
          source: crlfSource,
        })),
      })

      expect(view.state.doc).toBe(document)
      expect(toString).toHaveBeenCalled()
      view.dom.querySelector<HTMLButtonElement>('button')?.click()
      expect(onNavigate).toHaveBeenCalledWith('note:research')
    } finally {
      view.destroy()
    }
  })

  it('matches a raw UTF-8 wiki-link span through lone CR and CRLF normalization', () => {
    const source = 'a\ré\r\n[[Research]]'
    const prefix = 'a\ré\r\n'
    const onNavigate = vi.fn()
    const extension = livePreviewExtension({
      links: [{
        id: 'link:research',
        source_note_id: 'note:plan',
        target_note_id: 'note:research',
        target_note_title: 'Research',
        target_relative_path: 'pages/research.md',
        target_text: 'Research',
        link_kind: 'wikilink',
        resolved: true,
        source_start: new TextEncoder().encode(prefix).length,
        source_end: new TextEncoder().encode(source).length,
      }],
      onNavigate,
      source,
    })
    const view = new EditorView({
      state: EditorState.create({
        doc: source,
        extensions: [markdown({ base: markdownLanguage }), extension],
      }),
    })
    const editorPrefix = 'a\né\n'

    try {
      expect(view.state.doc.toString()).toBe(`${editorPrefix}[[Research]]`)
      view.dom.querySelector<HTMLButtonElement>('button')?.click()
      expect(onNavigate).toHaveBeenCalledWith('note:research')
      expect(view.moveByChar(EditorSelection.cursor(editorPrefix.length), true).head)
        .toBe(view.state.doc.length)
    } finally {
      view.destroy()
    }
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
