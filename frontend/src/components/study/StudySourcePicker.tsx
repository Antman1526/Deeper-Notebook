'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

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
  onSourceLinked?: (sourceId: string) => void | Promise<void>
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
  onSourceLinked,
  sources: providedSources,
  className,
}: StudySourcePickerProps) {
  const [loadedSources, setLoadedSources] = useState<StudySourceOption[]>([])
  const [fetchState, setFetchState] = useState<'loading' | 'ready' | 'error'>(
    providedSources === undefined ? 'loading' : 'ready',
  )
  const [retryCount, setRetryCount] = useState(0)
  const [linkError, setLinkError] = useState<{ sourceId: string } | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const initialLinkedIds = new Set(links.map(sourceId))
  const [linkedIds, setLinkedIds] = useState<Set<string>>(initialLinkedIds)
  const linkedIdsRef = useRef<Set<string>>(initialLinkedIds)
  const pendingIdsRef = useRef<Set<string>>(new Set())
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (providedSources !== undefined) {
      setFetchState('ready')
      setLoadedSources([])
      return
    }
    let active = true
    setFetchState('loading')
    void sourcesApi
      .list()
      .then((result) => {
        if (active && mountedRef.current) {
          setLoadedSources(result as StudySourceOption[])
          setFetchState('ready')
        }
      })
      .catch(() => {
        if (active && mountedRef.current) setFetchState('error')
      })
    return () => {
      active = false
    }
  }, [providedSources, retryCount])

  const sources = providedSources ?? loadedSources
  useEffect(() => {
    setLinkedIds((current) => {
      const next = new Set(current)
      links.forEach((link) => next.add(sourceId(link)))
      linkedIdsRef.current = next
      return next
    })
  }, [links])

  const linkSource = useCallback(
    async (id: string): Promise<boolean> => {
      if (linkedIdsRef.current.has(id) || pendingIdsRef.current.has(id)) return false
      pendingIdsRef.current.add(id)
      setPendingIds((current) => new Set(current).add(id))
      setLinkError(null)
      try {
        await onLinkSource?.(id)
      } catch {
        pendingIdsRef.current.delete(id)
        if (mountedRef.current) {
          setLinkError({ sourceId: id })
          setPendingIds((current) => {
            const next = new Set(current)
            next.delete(id)
            return next
          })
        }
        return false
      }
      if (!mountedRef.current) return false
      linkedIdsRef.current.add(id)
      pendingIdsRef.current.delete(id)
      setLinkError((current) => (current?.sourceId === id ? null : current))
      setLinkedIds((current) => new Set(current).add(id))
      setPendingIds((current) => {
        const next = new Set(current)
        next.delete(id)
        return next
      })
      try {
        await onSourceLinked?.(id)
      } catch {
        // A post-link refresh callback must not turn a successful link into a
        // false link failure.
      }
      return true
    },
    [onLinkSource, onSourceLinked],
  )

  const failedSourceTitle = linkError
    ? sources.find((source) => source.id === linkError.sourceId)?.title?.trim() || 'source'
    : 'source'

  const retryFailedLink = useCallback(() => {
    if (linkError) void linkSource(linkError.sourceId)
  }, [linkError, linkSource])

  const handleSourceCreated = useCallback(
    async (id: string) => {
      const normalizedId = id.trim()
      if (!normalizedId) return
      const linked = await linkSource(normalizedId)
      if (linked && mountedRef.current) await onSourceCreated?.(normalizedId)
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

      {fetchState === 'loading' ? (
        <p role="status" className="rounded-md border p-4 text-sm text-muted-foreground">
          Loading sources…
        </p>
      ) : fetchState === 'error' ? (
        <div className="space-y-3 rounded-md border border-destructive/40 p-4">
          <p role="alert" className="text-sm text-destructive">
            Unable to load sources.
          </p>
          <Button type="button" variant="outline" onClick={() => setRetryCount((count) => count + 1)}>
            Retry sources
          </Button>
        </div>
      ) : (
        <>
          {linkError ? (
            <div className="space-y-3 rounded-md border border-destructive/40 p-4">
              <p role="alert" className="text-sm text-destructive">
                Unable to link source.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={pendingIds.has(linkError.sourceId)}
                  onClick={retryFailedLink}
                >
                  Retry link {failedSourceTitle}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="Dismiss link error"
                  onClick={() => setLinkError(null)}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          ) : null}
          {sources.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No sources are available yet.
            </p>
          ) : (
            <ul role="list" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {sources.map((source) => {
                const id = source.id
                const linked = linkedIds.has(id)
                const pending = pendingIds.has(id)
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
                      disabled={linked || pending}
                      aria-label={linked ? `${source.title || 'Source'} linked` : `Link ${source.title || 'source'}`}
                      onClick={() => void linkSource(id)}
                    >
                      {linked ? 'Linked' : pending ? 'Linking…' : 'Link source'}
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
