'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { sourcesApi } from '@/lib/api/sources'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SOURCE_KIND_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

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
  /**
   * The first callback preserves existing per-source upload openers.  New
   * AddSourceDialog composition may use the second callback to deliver one
   * bounded batch without changing those existing callers.
   */
  onOpenUpload: (
    onSourceCreated?: (sourceId: string) => void | Promise<void>,
    onSourcesCreated?: (sourceIds: readonly string[]) => void | Promise<void>,
  ) => void
  /** Persists the plan link; a source is not marked linked until this succeeds. */
  onLinkSource: (sourceId: string) => void | Promise<void>
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
  labelKey: string
  variant: 'default' | 'secondary' | 'destructive' | 'outline'
} {
  if (source.status === 'failed') return { labelKey: 'study.studySourcePicker.status.unavailable', variant: 'destructive' }
  if (
    PROCESSING_STATUSES.has(source.status ?? '') ||
    source.extraction_quality === 'pending' ||
    source.extraction_quality === 'no_text' ||
    source.extraction_quality === 'low_text'
  ) {
    return { labelKey: 'study.studySourcePicker.status.processing', variant: 'secondary' }
  }
  if (source.status === 'completed' || source.extraction_quality === 'ok') {
    return { labelKey: 'study.studySourcePicker.status.ready', variant: 'default' }
  }
  return { labelKey: 'study.studySourcePicker.status.checking', variant: 'outline' }
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
  const { t } = useTranslation()
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
      if (typeof onLinkSource !== 'function') {
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
      try {
        await onLinkSource(id)
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
    ? sources.find((source) => source.id === linkError.sourceId)?.title?.trim() || t('study.studySourcePicker.sourceFallback')
    : t('study.studySourcePicker.sourceFallback')

  const retryFailedLink = useCallback(() => {
    if (linkError) void linkSource(linkError.sourceId)
  }, [linkError, linkSource])

  const handleSourceCreated = useCallback(
    async (id: string) => {
      const normalizedId = typeof id === 'string' ? id.trim() : ''
      if (!normalizedId) return
      const linked = await linkSource(normalizedId)
      if (linked && mountedRef.current) await onSourceCreated?.(normalizedId)
    },
    [linkSource, onSourceCreated],
  )

  const handleSourcesCreated = useCallback(
    async (ids: readonly string[]) => {
      for (const id of ids.slice(0, 50)) {
        await handleSourceCreated(id)
      }
    },
    [handleSourceCreated],
  )

  return (
    <section
      aria-labelledby="study-source-picker-title"
      className={className ?? 'space-y-4'}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="study-source-picker-title" className="text-base font-semibold">
            {t('study.studySourcePicker.heading')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('study.studySourcePicker.description')}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => onOpenUpload(handleSourceCreated, handleSourcesCreated)}
        >
          {t('study.studySourcePicker.upload')}
        </Button>
      </div>

      {fetchState === 'loading' ? (
        <p role="status" className="rounded-md border p-4 text-sm text-muted-foreground">
          {t('study.studySourcePicker.loading')}
        </p>
      ) : fetchState === 'error' ? (
        <div className="space-y-3 rounded-md border border-destructive/40 p-4">
          <p role="alert" className="text-sm text-destructive">
            {t('study.studySourcePicker.loadError')}
          </p>
          <Button type="button" variant="outline" onClick={() => setRetryCount((count) => count + 1)}>
            {t('study.studySourcePicker.retrySources')}
          </Button>
        </div>
      ) : (
        <>
          {linkError ? (
            <div className="space-y-3 rounded-md border border-destructive/40 p-4">
              <p role="alert" className="text-sm text-destructive">
                {t('study.studySourcePicker.linkError')}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={pendingIds.has(linkError.sourceId)}
                  onClick={retryFailedLink}
                >
                  {t('study.studySourcePicker.retryLink', { title: failedSourceTitle })}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={t('study.studySourcePicker.dismissLinkError')}
                  onClick={() => setLinkError(null)}
                >
                  {t('study.studySourcePicker.dismiss')}
                </Button>
              </div>
            </div>
          ) : null}
          {sources.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              {t('study.studySourcePicker.empty')}
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
                        {source.title?.trim() || t('study.studySourcePicker.untitled')}
                      </p>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="capitalize">{enumLabel(t, SOURCE_KIND_KEYS, sourceKind(source), spacedEnum(sourceKind(source)))}</span>
                        <Badge variant={state.variant}>{t(state.labelKey)}</Badge>
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant={linked ? 'secondary' : 'default'}
                      size="sm"
                      disabled={linked || pending}
                      aria-label={linked
                        ? t('study.studySourcePicker.linkedAria', { title: source.title || t('study.studySourcePicker.sourceFallbackCapital') })
                        : t('study.studySourcePicker.linkAria', { title: source.title || t('study.studySourcePicker.sourceFallback') })}
                      onClick={() => void linkSource(id)}
                    >
                      {linked ? t('study.studySourcePicker.linked') : pending ? t('study.studySourcePicker.linking') : t('study.studySourcePicker.link')}
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
