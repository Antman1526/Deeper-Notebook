import type { Content, Link, Root, Text } from 'mdast'

import type { VaultLink } from '@/lib/api/vault'

interface VFileLike {
  value?: string | Uint8Array
}

interface Point {
  line: number
  column: number
  offset: number
}

interface Position {
  start: Point
  end: Point
}

export interface MarkdownSourceIndex {
  byteOffset: (offset: number) => number
  position: (start: number, end: number) => Position
}

const wikiLinkExpression = /\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g
const anchorBearingParents = new Set([
  'code',
  'definition',
  'html',
  'image',
  'imageReference',
  'inlineCode',
  'link',
  'linkReference',
])

function utf8Width(codeUnit: number, nextCodeUnit: number | undefined): { bytes: number; units: number } {
  if (codeUnit <= 0x7f) return { bytes: 1, units: 1 }
  if (codeUnit <= 0x7ff) return { bytes: 2, units: 1 }
  if (codeUnit >= 0xd800 && codeUnit <= 0xdbff && nextCodeUnit !== undefined && nextCodeUnit >= 0xdc00 && nextCodeUnit <= 0xdfff) {
    return { bytes: 4, units: 2 }
  }
  return { bytes: 3, units: 1 }
}

export function createMarkdownSourceIndex(markdown: string): MarkdownSourceIndex {
  const byteOffsets = new Array<number>(markdown.length + 1)
  const lines = new Array<number>(markdown.length + 1)
  const columns = new Array<number>(markdown.length + 1)
  let byteOffset = 0
  let line = 1
  let column = 1
  let offset = 0

  while (offset < markdown.length) {
    byteOffsets[offset] = byteOffset
    lines[offset] = line
    columns[offset] = column
    const codeUnit = markdown.charCodeAt(offset)
    const width = utf8Width(codeUnit, offset + 1 < markdown.length ? markdown.charCodeAt(offset + 1) : undefined)

    if (width.units === 2) {
      byteOffsets[offset + 1] = byteOffset + 3
      lines[offset + 1] = line
      columns[offset + 1] = column + 1
      byteOffset += width.bytes
      column += 2
      offset += 2
      continue
    }

    byteOffset += width.bytes
    offset += 1
    if (codeUnit === 0x0d) {
      line += 1
      column = 1
    } else if (codeUnit === 0x0a) {
      if (offset < 2 || markdown.charCodeAt(offset - 2) !== 0x0d) line += 1
      column = 1
    } else {
      column += 1
    }
  }

  byteOffsets[markdown.length] = byteOffset
  lines[markdown.length] = line
  columns[markdown.length] = column

  const point = (requestedOffset: number): Point => {
    const boundedOffset = Math.max(0, Math.min(markdown.length, requestedOffset))
    return {
      line: lines[boundedOffset],
      column: columns[boundedOffset],
      offset: boundedOffset,
    }
  }

  return {
    byteOffset: (requestedOffset) => byteOffsets[Math.max(0, Math.min(markdown.length, requestedOffset))],
    position: (start, end) => ({ start: point(start), end: point(end) }),
  }
}

export function vaultLinkSpanKey(start: number, end: number): string {
  return `${start}:${end}`
}

export function buildUniqueResolvedSpanMap(links: VaultLink[]): Map<string, VaultLink> {
  const recordsBySpan = new Map<string, VaultLink | null>()
  for (const link of links) {
    const key = vaultLinkSpanKey(link.source_start, link.source_end)
    recordsBySpan.set(key, recordsBySpan.has(key) ? null : link)
  }

  const unique = new Map<string, VaultLink>()
  for (const [key, link] of recordsBySpan) {
    if (
      link?.resolved
      && link.target_note_id !== null
      && link.target_note_id !== undefined
      && link.target_note_title !== null
      && link.target_note_title !== undefined
      && link.target_relative_path !== null
      && link.target_relative_path !== undefined
    ) {
      unique.set(key, link)
    }
  }
  return unique
}

function textNode(index: MarkdownSourceIndex, value: string, start: number): Text {
  return {
    type: 'text',
    value,
    position: index.position(start, start + value.length),
  }
}

function wikiLinkNode(
  index: MarkdownSourceIndex,
  resolvedSpans: Map<string, VaultLink>,
  target: string,
  label: string,
  labelStart: number,
  start: number,
  end: number,
): Link {
  const sourceStart = index.byteOffset(start)
  const sourceEnd = index.byteOffset(end)
  const resolved = resolvedSpans.get(vaultLinkSpanKey(sourceStart, sourceEnd))
  return {
    type: 'link',
    url: '',
    title: null,
    children: [textNode(index, label, labelStart)],
    position: index.position(start, end),
    data: {
      hName: 'a',
      hProperties: {
        'data-vault-link': 'wiki',
        'data-vault-target': target,
        'data-vault-target-note': resolved?.target_note_id,
        'data-source-start': sourceStart,
        'data-source-end': sourceEnd,
      },
    },
  }
}

function splitTextNode(
  index: MarkdownSourceIndex,
  resolvedSpans: Map<string, VaultLink>,
  node: Text,
): Content[] | undefined {
  const start = node.position?.start.offset
  if (start === undefined) return undefined

  const children: Content[] = []
  let cursor = 0
  let match: RegExpExecArray | null
  wikiLinkExpression.lastIndex = 0

  while ((match = wikiLinkExpression.exec(node.value)) !== null) {
    const matchStart = start + match.index
    const matchEnd = matchStart + match[0].length
    if (match.index > cursor) {
      children.push(textNode(index, node.value.slice(cursor, match.index), start + cursor))
    }
    const target = match[1].trim()
    const rawLabel = match[2] ?? match[1]
    const label = rawLabel.trim()
    const labelInMatch = match[2] === undefined ? 2 : match[0].indexOf('|') + 1
    const labelStart = matchStart + labelInMatch + (rawLabel.length - rawLabel.trimStart().length)
    children.push(wikiLinkNode(index, resolvedSpans, target, label, labelStart, matchStart, matchEnd))
    cursor = match.index + match[0].length
  }

  if (children.length === 0) return undefined
  if (cursor < node.value.length) {
    children.push(textNode(index, node.value.slice(cursor), start + cursor))
  }
  return children
}

function transformChildren(
  index: MarkdownSourceIndex,
  resolvedSpans: Map<string, VaultLink>,
  node: { type?: string; children?: Content[] },
): void {
  if (!node.children || anchorBearingParents.has(node.type || '')) return

  const transformed: Content[] = []
  for (const child of node.children) {
    if (child.type === 'text') {
      transformed.push(...(splitTextNode(index, resolvedSpans, child) || [child]))
      continue
    }
    transformChildren(index, resolvedSpans, child)
    transformed.push(child)
  }
  node.children = transformed
}

export function remarkVaultLinks(options: {
  links: VaultLink[]
  sourceIndex?: MarkdownSourceIndex
  resolvedSpans?: Map<string, VaultLink>
}) {
  return (tree: Root, file: VFileLike): void => {
    if (typeof file.value !== 'string') return
    const index = options.sourceIndex || createMarkdownSourceIndex(file.value)
    const resolvedSpans = options.resolvedSpans || buildUniqueResolvedSpanMap(options.links)
    transformChildren(index, resolvedSpans, tree)
  }
}
