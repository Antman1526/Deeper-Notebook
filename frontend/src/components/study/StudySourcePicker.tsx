'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

import { sourcesApi } from '@/lib/api/sources'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

export interface StudySourceLink {
  source_id: string
}
/**
 * The picker consumes the existing source-list projection.  Deliberately do
 * not type this as SourceDetailResponse: source bodies and local asset paths
 * are not needed to link a source to a plan.
 */
export interface StudySourceOption {
  id: string
  title?: string | null
  source_type?: string | null
  status?: string | null
  command_id?: string | null
  extraction_quality?: 'pending' | 'no_text' | 'low_text' | 'ok' | null
  // These fields can arrive from a detail-shaped test fixture, but are never
  // rendered by this component.
  full_text?: string | null
  asset?: { file_path?: string; url?: string } | null
}

export interface StudySourcePickerProps {
  links: readonly StudySourceLink[] | readonly string[]
  onOpenUpload: (onSourceCreated?: (sourceId: string) => void) => void
  onLinkSource?: (sourceId: string) => void | Promise<void>
  onSourceCreated?: (sourceId: string) => void | Promise<void>
  sources?: readonly StudySourceOption[]
  className?: string
}

const PROCESSING_STATUSES = new Set(['new', 'queued', 'running'])

function sourceId(link: StudySourceLink | string): string {
  return typeof link === 'string' ? link : link.source_id
}

function sourceKind(source: StudySourceOption): string {
  if (source.source_type) return source.source_type
  if (source.asset?.url) return 'link'
  if (source.asset?.file_path) return 'upload'
  return 'text'
}

function readiness(source: StudySourceOption): {
  label: string
  variant: 'default' | 'secondary' | 'destructive' | 'outline'
} {
  if (source.status === 'failed') return { label: 'Unavailable', variant: 'destructive' }
  if (
    PROCESSING_STATUSES.has(source.status ?? '') ||
    source.extraction_quality === 'pending' ||
    source.extraction_quality === 'no_text' ||
    source.extraction_quality === 'low_text'
  ) {
    return { label: 'Processing', variant: 'secondary' }
  }
  if (source.status === 'completed' || source.extraction_quality === 'ok') {
    return { label: 'Ready', variant: 'default' }
  }
  return { label: 'Checking', variant: 'outline' }
}

/** Pick an existing source; upload remains owned by the existing dialog. */
export function StudySourcePicker({
  links,
  onOpenUpload,
  onLinkSource,
  onSourceCreated,
  sources: providedSources,
  className,
}: StudySourcePickerProps) {
  const [loadedSources, setLoadedSources] = useState<StudySourceOption[]>([])

  useEffect(() => {
    if (providedSources !== undefined) return
    let active = true
    void sourcesApi
      .list()
      .then((result) => {
        if (active) setLoadedSources(result as StudySourceOption[])
      })
      .catch(() => {
        // The picker remains usable for upload/link callbacks when the list
        // endpoint is unavailable; the API owns the eventual error contract.
      })
    return () => {
      active = false
    }
  }, [providedSources])

  const sources = providedSources ?? loadedSources
  const linkedIds = useMemo(() => new Set(links.map(sourceId)), [links])

  const linkSource = useCallback(
    (id: string) => {
      if (linkedIds.has(id)) return
      void onLinkSource?.(id)
    },
    [linkedIds, onLinkSource],
  )

  const handleSourceCreated = useCallback(
    (id: string) => {
      const normalizedId = id.trim()
      if (!normalizedId) return
      linkSource(normalizedId)
      void onSourceCreated?.(normalizedId)
    },
    [linkSource, onSourceCreated],
  )

  return (
    <section
      aria-labelledby="study-source-picker-title"
      className={className ?? 'space-y-4'}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="study-source-picker-title" className="text-base font-semibold">
            Learning sources
          </h2>
          <p className="text-sm text-muted-foreground">
            Reuse a source from your library or add one with the existing source dialog.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => onOpenUpload(handleSourceCreated)}>
          Upload PDF or video
        </Button>
      </div>

      {sources.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No sources are available yet.
        </p>
      ) : (
        <ul role="list" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sources.map((source) => {
            const id = source.id
            const linked = linkedIds.has(id)
            const state = readiness(source)
            return (
              <li
                key={id}
                className="flex min-w-0 flex-col justify-between gap-3 rounded-lg border bg-card p-4 shadow-sm"
              >
                <div className="min-w-0 space-y-2">
                  <p className="truncate font-medium" title={source.title ?? undefined}>
                    {source.title?.trim() || 'Untitled source'}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="capitalize">{sourceKind(source).replaceAll('_', ' ')}</span>
                    <Badge variant={state.variant}>{state.label}</Badge>
                  </div>
                </div>
                <Button
                  type="button"
                  variant={linked ? 'secondary' : 'default'}
                  size="sm"
                  disabled={linked}
                  aria-label={linked ? `${source.title || 'Source'} linked` : `Link ${source.title || 'source'}`}
                  onClick={() => linkSource(id)}
                >
                  {linked ? 'Linked' : 'Link source'}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
