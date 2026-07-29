'use client'

import { cloneElement, createElement, isValidElement, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

import type { VaultLink } from '@/lib/api/vault'
import { buildMarkdownModel, type HeadingDescriptor } from '@/lib/vault/markdown-model'
import { remarkVaultLinks } from '@/lib/vault/remark-vault-links'

interface VaultMarkdownProps {
  noteId?: string
  headingIdPrefix?: string
  markdown: string
  links: VaultLink[]
  onNavigate: (noteId: string) => void
  onPreview?: (link: VaultLink) => void
  footnoteLabel?: string
}

function utf8ByteOffset(markdown: string, offset: number): number {
  return new TextEncoder().encode(markdown.slice(0, offset)).length
}

function isAttachment(href?: string): boolean {
  return Boolean(href && /\.(?:png|jpe?g|gif|webp|pdf|mp3|mp4|mov)$/i.test(href))
}

function sourceSpan(
  markdown: string,
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
    : { start: utf8ByteOffset(markdown, start), end: utf8ByteOffset(markdown, end) }
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
  markdown: string,
  modelHeadings: HeadingDescriptor[],
  headingIdPrefix: string,
  links: VaultLink[],
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
    a: ({ node, children, ...props }) => {
      const properties = props as Record<string, unknown>
      const href = typeof properties.href === 'string' ? properties.href : undefined
      const footnoteReference = Boolean(properties['data-footnote-ref'] || properties.dataFootnoteRef)
      const footnoteBackReference = Boolean(properties['data-footnote-backref'] || properties.dataFootnoteBackref)
      if (footnoteReference || footnoteBackReference) {
        return <a {...props} role={footnoteReference ? 'doc-noteref' : 'doc-backlink'}>{children}</a>
      }
      if (isAttachment(href)) {
        return <span className="text-muted-foreground">{children}</span>
      }
      const span = sourceSpan(markdown, node, properties)
      const link = span && links.find((candidate) => (
        candidate.resolved
        && candidate.target_note_id
        && candidate.source_start === span.start
        && candidate.source_end === span.end
      ))
      if (!link?.target_note_id) return <span>{children}</span>
      return (
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
    },
  }
}

export function VaultMarkdown({
  noteId = 'note',
  headingIdPrefix = 'vault',
  markdown,
  links,
  onNavigate,
  onPreview,
  footnoteLabel = 'Footnotes',
}: VaultMarkdownProps) {
  const model = buildMarkdownModel(markdown)
  const components = readingComponents(
    markdown,
    model.headings,
    headingIdPrefix,
    links,
    onNavigate,
    onPreview,
  )

  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-4 prose-a:text-primary">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, [remarkVaultLinks, { links }]]}
        rehypePlugins={[rehypeKatex]}
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
