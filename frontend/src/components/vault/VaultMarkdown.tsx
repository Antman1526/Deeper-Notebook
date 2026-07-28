'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'

import type { VaultLink } from '@/lib/api/vault'

function withResolvedLinks(markdown: string, links: VaultLink[]) {
  return markdown.replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (whole, target, alias) => {
    const link = links.find((candidate) => candidate.resolved && candidate.target_note_id && candidate.target_text === target.trim())
    return link?.target_note_id ? `[${alias?.trim() || target.trim()}](#vault-note:${link.target_note_id})` : whole
  })
}

function isAttachment(href?: string) { return Boolean(href && /\.(?:png|jpe?g|gif|webp|pdf|mp3|mp4|mov)$/i.test(href)) }

export function VaultMarkdown({ markdown, links, onNavigate }: { markdown: string; links: VaultLink[]; onNavigate: (noteId: string) => void }) {
  return <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-4 prose-a:text-primary">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} components={{
      a: ({ href, children }) => href?.startsWith('#vault-note:') ? <button type="button" className="font-medium text-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onNavigate(href.slice('#vault-note:'.length))}>{children}</button> : isAttachment(href) ? <span className="text-muted-foreground">{children}</span> : <span>{children}</span>,
    }}>{withResolvedLinks(markdown, links)}</ReactMarkdown>
  </div>
}
