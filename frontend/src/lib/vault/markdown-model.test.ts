import { describe, expect, it } from 'vitest'

import { buildMarkdownModel } from './markdown-model'

describe('buildMarkdownModel', () => {
  it('extracts six heading levels and stable duplicate slugs', () => {
    const model = buildMarkdownModel([
      '# Plan',
      '## Evidence',
      '###### Detail',
      '# Plan',
    ].join('\n'))

    expect(model.headings).toEqual([
      expect.objectContaining({ level: 1, text: 'Plan', slug: 'plan' }),
      expect.objectContaining({ level: 2, text: 'Evidence', slug: 'evidence' }),
      expect.objectContaining({ level: 6, text: 'Detail', slug: 'detail' }),
      expect.objectContaining({ level: 1, text: 'Plan', slug: 'plan-1' }),
    ])
  })

  it('does not treat fenced code headings as document headings', () => {
    const model = buildMarkdownModel([
      '```md',
      '# Not an outline item',
      '```',
      '# Real heading',
    ].join('\n'))

    expect(model.headings.map((heading) => heading.text))
      .toEqual(['Real heading'])
  })

  it('records source ranges for supported live-preview constructs', () => {
    const markdown = '# Plan\n\n**strong** and [[Evidence]] and `code`'
    const model = buildMarkdownModel(markdown)

    expect(model.constructs.map((construct) => construct.kind))
      .toEqual(expect.arrayContaining([
        'heading',
        'strong',
        'wikilink',
        'inline-code',
      ]))
    expect(model.constructs.every((construct) =>
      construct.from >= 0
      && construct.to > construct.from
      && construct.to <= markdown.length,
    )).toBe(true)
  })

  it('includes the marker in a start-of-document tag range', () => {
    const markdown = '#tag'
    const tag = buildMarkdownModel(markdown).constructs
      .find((construct) => construct.kind === 'tag')

    expect(tag).toEqual({ kind: 'tag', from: 0, to: 4 })
    expect(markdown.slice(tag?.from, tag?.to)).toBe('#tag')
  })

  it('keeps fragment tags and nested wiki links out of constructs', () => {
    const markdown = '[outline](#fragment) [[#inside-wiki-heading]]'
    const relevant = buildMarkdownModel(markdown).constructs
      .filter((construct) =>
        construct.kind === 'link'
        || construct.kind === 'tag'
        || construct.kind === 'wikilink',
      )

    expect(relevant).toEqual([
      { kind: 'link', from: 0, to: 20 },
      { kind: 'wikilink', from: 21, to: 45 },
    ])
  })

  it.each(['\n', '\r\n'])(
    'strips an indented Setext underline with %j newlines',
    (newline) => {
      const markdown = `Setext title${newline}  ===`

      expect(buildMarkdownModel(markdown).headings).toEqual([
        {
          level: 1,
          text: 'Setext title',
          slug: 'setext-title',
          sourceFrom: 0,
          sourceTo: markdown.length,
        },
      ])
    },
  )

  it('keeps regex exclusion work linear for adversarial Markdown', () => {
    const count = 200
    const markdown = Array.from(
      { length: count },
      (_, index) => `\`#hidden-${index}\` #visible-${index}`,
    ).join('\n')
    const originalSome = Array.prototype.some
    let predicateVisits = 0

    function instrumentedSome<T>(
      this: T[],
      predicate: (value: T, index: number, array: T[]) => unknown,
      thisArg?: unknown,
    ): boolean {
      for (let index = 0; index < this.length; index += 1) {
        if (!(index in this)) continue
        predicateVisits += 1
        if (predicate.call(thisArg, this[index], index, this)) return true
      }
      return false
    }

    let model: ReturnType<typeof buildMarkdownModel> | undefined
    Array.prototype.some = instrumentedSome as typeof Array.prototype.some
    try {
      model = buildMarkdownModel(markdown)
    } finally {
      Array.prototype.some = originalSome
    }

    expect(model?.constructs.filter((construct) => construct.kind === 'tag'))
      .toHaveLength(count)
    expect(predicateVisits).toBeLessThan(count * 20)
  })
})
