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

const wikiLinkExpression = /\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g

function utf8ByteOffset(markdown: string, offset: number): number {
  return new TextEncoder().encode(markdown.slice(0, offset)).length
}

function pointAt(markdown: string, offset: number): Point {
  const prefix = markdown.slice(0, offset)
  const lastLineBreak = Math.max(prefix.lastIndexOf('\n'), prefix.lastIndexOf('\r'))
  return {
    line: prefix.split(/\r\n|\r|\n/).length,
    column: offset - lastLineBreak,
    offset,
  }
}

function positionAt(markdown: string, start: number, end: number): Position {
  return {
    start: pointAt(markdown, start),
    end: pointAt(markdown, end),
  }
}

function textNode(markdown: string, value: string, start: number): Text {
  return {
    type: 'text',
    value,
    position: positionAt(markdown, start, start + value.length),
  }
}

function wikiLinkNode(
  markdown: string,
  target: string,
  label: string,
  start: number,
  end: number,
): Link {
  return {
    type: 'link',
    url: '',
    title: null,
    children: [textNode(markdown, label, start)],
    position: positionAt(markdown, start, end),
    data: {
      hName: 'a',
      hProperties: {
        'data-vault-link': 'wiki',
        'data-vault-target': target,
        'data-source-start': utf8ByteOffset(markdown, start),
        'data-source-end': utf8ByteOffset(markdown, end),
      },
    },
  }
}

function splitTextNode(markdown: string, node: Text): Content[] | undefined {
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
      children.push(textNode(markdown, node.value.slice(cursor, match.index), start + cursor))
    }
    const target = match[1].trim()
    const label = (match[2] || target).trim()
    children.push(wikiLinkNode(markdown, target, label, matchStart, matchEnd))
    cursor = match.index + match[0].length
  }

  if (children.length === 0) return undefined
  if (cursor < node.value.length) {
    children.push(textNode(markdown, node.value.slice(cursor), start + cursor))
  }
  return children
}

function transformChildren(markdown: string, node: { type?: string; children?: Content[] }): void {
  if (!node.children || ['code', 'inlineCode', 'html', 'link', 'definition'].includes(node.type || '')) {
    return
  }

  const transformed: Content[] = []
  for (const child of node.children) {
    if (child.type === 'text') {
      transformed.push(...(splitTextNode(markdown, child) || [child]))
      continue
    }
    transformChildren(markdown, child)
    transformed.push(child)
  }
  node.children = transformed
}

export function remarkVaultLinks(options: { links: VaultLink[] }) {
  void options.links
  return (tree: Root, file: VFileLike): void => {
    if (typeof file.value !== 'string') return
    transformChildren(file.value, tree)
  }
}
