import { markdownLanguage } from '@codemirror/lang-markdown'

export type MarkdownConstructKind =
  | 'heading'
  | 'emphasis'
  | 'strong'
  | 'strikethrough'
  | 'inline-code'
  | 'fenced-code'
  | 'link'
  | 'wikilink'
  | 'task-marker'
  | 'blockquote'
  | 'horizontal-rule'
  | 'list-marker'
  | 'tag'
  | 'footnote'
  | 'math'

export interface HeadingDescriptor {
  level: 1 | 2 | 3 | 4 | 5 | 6
  text: string
  slug: string
  sourceFrom: number
  sourceTo: number
}

export interface MarkdownConstruct {
  kind: MarkdownConstructKind
  from: number
  to: number
}

export interface MarkdownModel {
  headings: HeadingDescriptor[]
  constructs: MarkdownConstruct[]
}

const constructKinds: Record<string, MarkdownConstructKind> = {
  Emphasis: 'emphasis',
  StrongEmphasis: 'strong',
  Strikethrough: 'strikethrough',
  InlineCode: 'inline-code',
  FencedCode: 'fenced-code',
  Link: 'link',
  TaskMarker: 'task-marker',
  Blockquote: 'blockquote',
  HorizontalRule: 'horizontal-rule',
  ListMark: 'list-marker',
}

function baseSlug(text: string): string {
  const slug = text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en-US')
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
  return slug || 'section'
}

function headingLevel(name: string): HeadingDescriptor['level'] | undefined {
  const match = /^(?:ATX|Setext)Heading([1-6])$/.exec(name)
  return match ? Number(match[1]) as HeadingDescriptor['level'] : undefined
}

function headingText(source: string, name: string): string {
  if (name.startsWith('ATX')) {
    return source
      .replace(/^ {0,3}#{1,6}[ \t]+/, '')
      .replace(/[ \t]+#+[ \t]*$/, '')
      .trim()
  }

  return source
    .replace(/\r?\n[=-]+[ \t]*$/, '')
    .trim()
}

function intersects({ from, to }: MarkdownConstruct, rangeFrom: number, rangeTo: number): boolean {
  return from < rangeTo && rangeFrom < to
}

function appendRegexConstructs(
  markdown: string,
  constructs: MarkdownConstruct[],
  excludedRanges: MarkdownConstruct[],
): void {
  const addMatches = (kind: 'wikilink' | 'tag', expression: RegExp, capture = 0) => {
    for (const match of markdown.matchAll(expression)) {
      const source = match[capture] ?? match[0]
      const from = (match.index ?? 0) + match[0].indexOf(source)
      const to = from + source.length
      if (!excludedRanges.some((range) => intersects(range, from, to))) {
        constructs.push({ kind, from, to })
      }
    }
  }

  addMatches('wikilink', /\[\[[^\]\r\n]{1,2048}\]\]/gu)
  addMatches('tag', /(?:^|[\s([{])(#[\p{Letter}\p{Number}_/-]{1,256})/gmu, 1)
}

function uniqueSortedConstructs(constructs: MarkdownConstruct[]): MarkdownConstruct[] {
  const seen = new Set<string>()

  return constructs
    .sort((left, right) => left.from - right.from || left.to - right.to)
    .filter((construct) => {
      const key = `${construct.kind}:${construct.from}:${construct.to}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function buildMarkdownModel(markdown: string): MarkdownModel {
  const headings: HeadingDescriptor[] = []
  const constructs: MarkdownConstruct[] = []
  const excludedRanges: MarkdownConstruct[] = []
  const slugCounts = new Map<string, number>()
  const tree = markdownLanguage.parser.parse(markdown)

  tree.iterate({
    enter: ({ from, name, to }) => {
      const level = headingLevel(name)
      if (level) {
        const text = headingText(markdown.slice(from, to), name)
        const slugBase = baseSlug(text)
        const count = slugCounts.get(slugBase) ?? 0
        slugCounts.set(slugBase, count + 1)
        headings.push({
          level,
          text,
          slug: count === 0 ? slugBase : `${slugBase}-${count}`,
          sourceFrom: from,
          sourceTo: to,
        })
        constructs.push({ kind: 'heading', from, to })
      }

      const kind = constructKinds[name]
      if (kind) {
        const construct = { kind, from, to }
        constructs.push(construct)
        if (kind === 'fenced-code' || kind === 'inline-code') {
          excludedRanges.push(construct)
        }
      }
    },
  })

  appendRegexConstructs(markdown, constructs, excludedRanges)

  return {
    headings,
    constructs: uniqueSortedConstructs(constructs),
  }
}
