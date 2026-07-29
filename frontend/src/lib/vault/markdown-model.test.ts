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
})
