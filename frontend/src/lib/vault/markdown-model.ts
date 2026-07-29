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

interface SourceRange {
  from: number
  to: number
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
    .replace(/\r?\n {0,3}[=-]+[ \t]*$/, '')
    .trim()
}

function collectRegexRanges(
  markdown: string,
  expression: RegExp,
  capture = 0,
): SourceRange[] {
  const ranges: SourceRange[] = []

  for (const match of markdown.matchAll(expression)) {
    const source = match[capture] ?? match[0]
    const from = (match.index ?? 0) + match[0].indexOf(source)
    ranges.push({ from, to: from + source.length })
  }

  return ranges
}

function mergeRanges(ranges: SourceRange[]): SourceRange[] {
  const sorted = [...ranges].sort(
    (left, right) => left.from - right.from || left.to - right.to,
  )
  const merged: SourceRange[] = []

  for (const range of sorted) {
    const previous = merged.at(-1)
    if (!previous || previous.to < range.from) {
      merged.push({ ...range })
      continue
    }
    previous.to = Math.max(previous.to, range.to)
  }

  return merged
}

function appendRangesOutsideExclusions(
  kind: 'wikilink' | 'tag',
  ranges: SourceRange[],
  constructs: MarkdownConstruct[],
  excludedRanges: SourceRange[],
): void {
  let exclusionIndex = 0

  for (const range of ranges) {
    while (
      exclusionIndex < excludedRanges.length
      && excludedRanges[exclusionIndex].to <= range.from
    ) {
      exclusionIndex += 1
    }

    const exclusion = excludedRanges[exclusionIndex]
    if (exclusion && exclusion.from < range.to) continue
    constructs.push({ kind, ...range })
  }
}

function isContainedBySortedRange(
  ranges: SourceRange[],
  from: number,
  to: number,
): boolean {
  let low = 0
  let high = ranges.length - 1

  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const range = ranges[middle]
    if (range.from > from) {
      high = middle - 1
    } else if (range.to < to) {
      low = middle + 1
    } else {
      return true
    }
  }

  return false
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
  const codeExclusions: SourceRange[] = []
  const tagExclusions: SourceRange[] = []
  const slugCounts = new Map<string, number>()
  const wikiRanges = collectRegexRanges(
    markdown,
    /\[\[[^\]\r\n]{1,2048}\]\]/gu,
  )
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
        if (
          kind !== 'link'
          || !isContainedBySortedRange(wikiRanges, from, to)
        ) {
          constructs.push(construct)
        }
        if (kind === 'fenced-code' || kind === 'inline-code') {
          codeExclusions.push({ from, to })
          tagExclusions.push({ from, to })
        } else if (kind === 'link') {
          tagExclusions.push({ from, to })
        }
      }

      if (name === 'URL') tagExclusions.push({ from, to })
    },
  })

  const mergedCodeExclusions = mergeRanges(codeExclusions)
  appendRangesOutsideExclusions(
    'wikilink',
    wikiRanges,
    constructs,
    mergedCodeExclusions,
  )

  const tagRanges = collectRegexRanges(
    markdown,
    /(?:^|[\s([{])(#[\p{Letter}\p{Number}_/-]{1,256})/gmu,
    1,
  )
  const mergedTagExclusions = mergeRanges([...tagExclusions, ...wikiRanges])
  appendRangesOutsideExclusions(
    'tag',
    tagRanges,
    constructs,
    mergedTagExclusions,
  )

  return {
    headings,
    constructs: uniqueSortedConstructs(constructs),
  }
}
