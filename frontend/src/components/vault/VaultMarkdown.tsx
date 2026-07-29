'use client'

import { cloneElement, createElement, isValidElement, type ReactNode } from 'react'
import type { Element, Root } from 'hast'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

import type { VaultLink } from '@/lib/api/vault'
import { buildMarkdownModel, type HeadingDescriptor } from '@/lib/vault/markdown-model'
import {
  buildUniqueResolvedSpanMap,
  createMarkdownSourceIndex,
  remarkVaultLinks,
  type MarkdownSourceIndex,
  vaultLinkSpanKey,
} from '@/lib/vault/remark-vault-links'
import { VaultPagePreview } from './VaultPagePreview'

interface VaultMarkdownProps {
  vaultId?: string
  noteId?: string
  headingIdPrefix?: string
  markdown: string
  links: VaultLink[]
  onNavigate: (noteId: string) => void
  onPreview?: (link: VaultLink) => void
  footnoteLabel?: string
}

function sanitizeIdPart(value: string): string {
  return value
    .normalize('NFKC')
    .toLocaleLowerCase('en-US')
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'view'
}

function walkElements(node: Root | Element, visitor: (element: Element) => void): void {
  if (node.type === 'element') visitor(node)
  for (const child of node.children) {
    if (child.type === 'element') walkElements(child, visitor)
  }
}

function rewriteIdReference(value: unknown, idMap: Map<string, string>): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => typeof item === 'string' ? idMap.get(item) || item : item)
  }
  if (typeof value !== 'string') return value
  return value.split(/\s+/).map((id) => idMap.get(id) || id).join(' ')
}

function rehypeViewScopedFootnotes(options: { viewPrefix: string }) {
  return (tree: Root): void => {
    const prefix = sanitizeIdPart(options.viewPrefix)
    const idMap = new Map<string, string>()
    walkElements(tree, (element) => {
      const id = element.properties.id
      if (typeof id === 'string') idMap.set(id, `${prefix}-${sanitizeIdPart(id)}`)
    })
    walkElements(tree, (element) => {
      const id = element.properties.id
      if (typeof id === 'string') element.properties.id = idMap.get(id) || id
      const href = element.properties.href
      if (typeof href === 'string' && href.startsWith('#')) {
        const target = idMap.get(href.slice(1))
        if (target) element.properties.href = `#${target}`
      }
      if ('ariaDescribedBy' in element.properties) {
        element.properties.ariaDescribedBy = rewriteIdReference(element.properties.ariaDescribedBy, idMap) as string | string[]
      }
      if ('aria-describedby' in element.properties) {
        element.properties['aria-describedby'] = rewriteIdReference(element.properties['aria-describedby'], idMap) as string | string[]
      }
    })
  }
}

function isAttachmentTarget(target?: string): boolean {
  if (!target) return false
  const path = target.trim().split(/[?#]/, 1)[0]
  return /\.(?:png|jpe?g|gif|webp|svg|pdf|mp3|mp4|mov)$/i.test(path)
}

function inertImageLabel(alt?: string, source?: string | Blob): string {
  if (alt?.trim()) return alt.trim()
  const path = typeof source === 'string' ? source.trim().split(/[?#]/, 1)[0] : ''
  const filename = path.split(/[\\/]/).at(-1) || ''
  try {
    return decodeURIComponent(filename) || 'Attachment'
  } catch {
    return filename || 'Attachment'
  }
}

function sourceSpan(
  index: MarkdownSourceIndex,
  node: { position?: { start?: { offset?: number }; end?: { offset?: number } } } | undefined,
  properties: Record<string, unknown>,
): { start: number; end: number } | undefined {
  const propertyStart = Number(properties['data-source-start'])
  const propertyEnd = Number(properties['data-source-end'])
  if (Number.isInteger(propertyStart) && Number.isInteger(propertyEnd)) {
    return { start: propertyStart, end: propertyEnd }
  }
  const start = node?.position?.start?.offset
  const end = node?.position?.end?.offset
  return start === undefined || end === undefined
    ? undefined
    : { start: index.byteOffset(start), end: index.byteOffset(end) }
}

function textContent(children: ReactNode): string {
  return Array.isArray(children)
    ? children.map(textContent).join('')
    : typeof children === 'string' || typeof children === 'number'
      ? String(children)
      : isValidElement<{ children?: ReactNode }>(children)
        ? textContent(children.props.children)
        : ''
}

function taskListItem({ children, ...props }: React.ComponentPropsWithoutRef<'li'>) {
  const label = textContent(children).trim()
  const labelledChildren = Array.isArray(children)
    ? children.map((child) => isValidElement<React.ComponentPropsWithoutRef<'input'>>(child) && child.type === 'input'
      ? cloneElement(child, { 'aria-label': label })
      : child)
    : children
  return <li {...props}>{labelledChildren}</li>
}

function headingComponent(
  tag: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6',
  level: HeadingDescriptor['level'],
  headings: HeadingDescriptor[],
  headingIdPrefix: string,
) {
  let cursor = 0
  return function Heading({ children, ...props }: React.ComponentPropsWithoutRef<typeof tag>) {
    if (props.id) return createElement(tag, props, children)
    const heading = headings[cursor] || {
      slug: `section-${cursor}`,
      text: textContent(children),
      level,
      sourceFrom: 0,
      sourceTo: 0,
    }
    cursor += 1
    return createElement(tag, {
      ...props,
      id: `${headingIdPrefix}-${heading.slug}`,
      'data-heading-slug': heading.slug,
    }, children)
  }
}

function readingComponents(
  vaultId: string | undefined,
  sourceIndex: MarkdownSourceIndex,
  modelHeadings: HeadingDescriptor[],
  headingIdPrefix: string,
  resolvedSpans: Map<string, VaultLink>,
  onNavigate: (noteId: string) => void,
  onPreview?: (link: VaultLink) => void,
): Components {
  const headingsByLevel = new Map<HeadingDescriptor['level'], HeadingDescriptor[]>()
  for (const heading of modelHeadings) {
    const current = headingsByLevel.get(heading.level) || []
    current.push(heading)
    headingsByLevel.set(heading.level, current)
  }

  return {
    h1: headingComponent('h1', 1, headingsByLevel.get(1) || [], headingIdPrefix),
    h2: headingComponent('h2', 2, headingsByLevel.get(2) || [], headingIdPrefix),
    h3: headingComponent('h3', 3, headingsByLevel.get(3) || [], headingIdPrefix),
    h4: headingComponent('h4', 4, headingsByLevel.get(4) || [], headingIdPrefix),
    h5: headingComponent('h5', 5, headingsByLevel.get(5) || [], headingIdPrefix),
    h6: headingComponent('h6', 6, headingsByLevel.get(6) || [], headingIdPrefix),
    li: taskListItem,
    img: ({ alt, src }) => (
      <span className="text-muted-foreground">{inertImageLabel(alt, src)}</span>
    ),
    a: ({ node, children, ...props }) => {
      const properties = props as Record<string, unknown>
      const href = typeof properties.href === 'string' ? properties.href : undefined
      const footnoteReference = Boolean(properties['data-footnote-ref'] || properties.dataFootnoteRef)
      const footnoteBackReference = Boolean(properties['data-footnote-backref'] || properties.dataFootnoteBackref)
      if (footnoteReference || footnoteBackReference) {
        return <a {...props} role={footnoteReference ? 'doc-noteref' : 'doc-backlink'}>{children}</a>
      }
      const wikiTarget = properties['data-vault-target'] ?? properties.dataVaultTarget
      const attachmentTarget = typeof wikiTarget === 'string' ? wikiTarget : href
      if (isAttachmentTarget(attachmentTarget)) {
        return <span className="text-muted-foreground">{children}</span>
      }
      const span = sourceSpan(sourceIndex, node, properties)
      const link = span && resolvedSpans.get(vaultLinkSpanKey(span.start, span.end))
      if (!link?.target_note_id) return <span>{children}</span>
      const trigger = (
        <button
          type="button"
          className="font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => onNavigate(link.target_note_id!)}
          onFocus={() => onPreview?.(link)}
          onMouseEnter={() => onPreview?.(link)}
        >
          {children}
        </button>
      )
      return vaultId ? (
        <VaultPagePreview
          vaultId={vaultId}
          link={link}
          onNavigate={onNavigate}
          trigger={trigger}
        />
      ) : trigger
    },
  }
}

export function VaultMarkdown({
  vaultId,
  noteId = 'note',
  headingIdPrefix = 'vault',
  markdown,
  links,
  onNavigate,
  onPreview,
  footnoteLabel = 'Footnotes',
}: VaultMarkdownProps) {
  const model = buildMarkdownModel(markdown)
  const sourceIndex = createMarkdownSourceIndex(markdown)
  const resolvedSpans = buildUniqueResolvedSpanMap(links)
  const components = readingComponents(
    vaultId,
    sourceIndex,
    model.headings,
    headingIdPrefix,
    resolvedSpans,
    onNavigate,
    onPreview,
  )

  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-4 prose-a:text-primary">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, [remarkVaultLinks, { links, sourceIndex, resolvedSpans }]]}
        rehypePlugins={[rehypeKatex, [rehypeViewScopedFootnotes, { viewPrefix: headingIdPrefix }]]}
        remarkRehypeOptions={{
          clobberPrefix: `dn-${noteId}-`,
          footnoteLabel,
        }}
        skipHtml
        components={components}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  )
}
