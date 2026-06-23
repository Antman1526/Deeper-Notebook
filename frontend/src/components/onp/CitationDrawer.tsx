'use client'

import { ExternalLink, Quote, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

export interface CitationEvidence {
  sourceId: string
  title: string
  preview?: string
  location?: string
}

function citationString(citation: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = citation[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

export function citationEvidenceFromRecord(
  citation: Record<string, unknown>,
  fallbackSourceId: string,
): CitationEvidence {
  const sourceId = citationString(citation, ['source_id', 'sourceId', 'id']) || fallbackSourceId
  const title = citationString(citation, ['title', 'source_title', 'sourceTitle']) || sourceId
  const preview = citationString(citation, ['preview', 'quote', 'excerpt', 'text'])
  const location = citationString(citation, ['location', 'marker', 'page', 'section', 'chunk'])

  return {
    sourceId,
    title,
    ...(preview ? { preview } : {}),
    ...(location ? { location } : {}),
  }
}

function sourceHref(sourceId: string): string {
  return `/sources/${encodeURIComponent(sourceId)}`
}

export function CitationDrawer({
  evidence,
  onClose,
}: {
  evidence: CitationEvidence | null
  onClose: () => void
}) {
  if (!evidence) return null

  return (
    <section
      aria-label="Citation evidence"
      className="mt-4 rounded-md border border-[var(--onp-evidence)] bg-background p-3 shadow-[var(--onp-elevation-low)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Quote className="h-4 w-4 text-[var(--onp-evidence)]" aria-hidden="true" />
            Citation evidence
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{evidence.title}</div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label="Close citation evidence"
          onClick={onClose}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>

      <dl className="mt-3 space-y-2 text-xs">
        <div>
          <dt className="font-medium text-muted-foreground">Source ID</dt>
          <dd className="mt-1 break-all text-foreground">{evidence.sourceId}</dd>
        </div>
        {evidence.location && (
          <div>
            <dt className="font-medium text-muted-foreground">Location</dt>
            <dd className="mt-1 text-foreground">{evidence.location}</dd>
          </div>
        )}
      </dl>

      {evidence.preview ? (
        <blockquote className="mt-3 border-l-2 border-[var(--onp-accent-strong)] pl-3 text-sm leading-6 text-foreground">
          {evidence.preview}
        </blockquote>
      ) : (
        <div className="mt-3 rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          No quote preview is stored for this citation yet.
        </div>
      )}

      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
        <a href={sourceHref(evidence.sourceId)}>
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
          Open source record
        </a>
      </Button>
    </section>
  )
}
