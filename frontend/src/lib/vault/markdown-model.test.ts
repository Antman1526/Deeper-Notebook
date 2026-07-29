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

  it('does not create a wikilink inside a Markdown link destination', () => {
    const markdown = '[outer](https://example.test/[[inner]])'
    const relevant = buildMarkdownModel(markdown).constructs
      .filter((construct) =>
        construct.kind === 'link' || construct.kind === 'wikilink',
      )

    expect(relevant).toEqual([
      { kind: 'link', from: 0, to: markdown.length },
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

  it('scales across a large adversarial Markdown document', () => {
    const count = 20_000
    const markdown = Array.from(
      { length: count },
      (_, index) => `\`#hidden-${index}\` #visible-${index}`,
    ).join('\n')
    const tags = buildMarkdownModel(markdown).constructs
      .filter((construct) => construct.kind === 'tag')
    const finalTag = `#visible-${count - 1}`

    expect(tags).toHaveLength(count)
    expect(tags[0]).toEqual({
      kind: 'tag',
      from: markdown.indexOf('#visible-0'),
      to: markdown.indexOf('#visible-0') + '#visible-0'.length,
    })
    expect(tags.at(-1)).toEqual({
      kind: 'tag',
      from: markdown.lastIndexOf(finalTag),
      to: markdown.lastIndexOf(finalTag) + finalTag.length,
    })
  }, 5_000)
})
