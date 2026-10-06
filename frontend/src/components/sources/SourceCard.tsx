'use client'

import React, { Fragment, useState, useEffect, useRef } from 'react'
import { SourceListResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import {
  FileText,
  ExternalLink,
  Upload,
  MoreVertical,
  Trash2,
  RefreshCw,
  Clock,
  CheckCircle,
  AlertTriangle,
  Loader2,
  Unlink,
  Podcast
} from 'lucide-react'
import { useSourceStatus } from '@/lib/hooks/use-sources'
import { useTranslation } from '@/lib/hooks/use-translation'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'
import type { TFunction } from 'i18next'
import { cn } from '@/lib/utils'
import { ContextToggle } from '@/components/common/ContextToggle'
import { ContextMode } from '@/app/(dashboard)/notebooks/[id]/page'
import { SourceCover } from '@/components/deeper-notebook/source-gallery/SourceCover'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useSourceVisualsEnabled } from '@/lib/features-client'

interface SourceCardProps {
  source: SourceListResponse
  onDelete?: (sourceId: string) => void
  onRetry?: (sourceId: string) => void
  onRemoveFromNotebook?: (sourceId: string) => void
  onClick?: (sourceId: string) => void
  onRefresh?: () => void
  className?: string
  showRemoveFromNotebook?: boolean
  showVisualCover?: boolean
  contextMode?: ContextMode
  onContextModeChange?: (mode: ContextMode) => void
  // v0.8.128 — explicit notebookId scoping when rendered inside a notebook
  notebookId?: string | null
}

const SOURCE_TYPE_ICONS = {
  link: ExternalLink,
  upload: Upload,
  text: FileText,
  web_import: ExternalLink,
  deep_research_report: FileText,
} as const

// v0.8.130 — status colours from theme tokens: info for in-flight, success for done (UI audit Phase 1)
const getStatusConfig = (t: TFunction) => ({
  new: {
    icon: Clock,
    color: 'text-info-ink',
    bgColor: 'bg-info-soft',
    borderColor: 'border-info/30',
    label: t('sources.statusProcessing'),
    description: t('sources.statusPreparingDesc')
  },
  queued: {
    icon: Clock,
    color: 'text-info-ink',
    bgColor: 'bg-info-soft',
    borderColor: 'border-info/30',
    label: t('sources.statusQueued'),
    description: t('sources.statusQueuedDesc')
  },
  running: {
    icon: Loader2,
    color: 'text-info-ink',
    bgColor: 'bg-info-soft',
    borderColor: 'border-info/30',
    label: t('sources.statusProcessing'),
    description: t('sources.statusProcessingDesc')
  },
  completed: {
    icon: CheckCircle,
    color: 'text-success-ink',
    bgColor: 'bg-success-soft',
    borderColor: 'border-success/30',
    label: t('sources.statusCompleted'),
    description: t('sources.statusCompletedDesc')
  },
  failed: {
    icon: AlertTriangle,
    color: 'text-destructive-ink',
    bgColor: 'bg-destructive-soft',
    borderColor: 'border-destructive/30',
    label: t('sources.statusFailed'),
    description: t('sources.statusFailedDesc')
  }
} as const)

type SourceStatus = 'new' | 'queued' | 'running' | 'completed' | 'failed'

function isSourceStatus(status: unknown): status is SourceStatus {
  return typeof status === 'string' && ['new', 'queued', 'running', 'completed', 'failed'].includes(status)
}

type SourceType = keyof typeof SOURCE_TYPE_ICONS

function getSourceType(source: SourceListResponse): SourceType {
  if (source.source_type && source.source_type in SOURCE_TYPE_ICONS) {
    return source.source_type as SourceType
  }
  // Determine type based on asset information
  if (source.asset?.url) return 'link'
  if (source.asset?.file_path) return 'upload'
  return 'text'
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function fileNameFromPath(path: string | undefined): string | null {
  if (!path) return null
  return path.split('/').filter(Boolean).at(-1) ?? null
}

function getSourceTypeLabel(sourceType: SourceType, t: TFunction): string {
  if (sourceType === 'link') return t('sources.addUrl')
  if (sourceType === 'upload') return t('sources.uploadFile')
  if (sourceType === 'web_import') return t('sources.sourceCard.webImport')
  if (sourceType === 'deep_research_report') return t('sources.sourceCard.deepResearch')
  return t('sources.enterText')
}

function getProvenanceLabel(source: SourceListResponse): string | null {
  const provenance = source.provenance ?? {}
  return (
    readString(provenance.domain) ??
    readString(provenance.original_filename) ??
    readString(provenance.file_name) ??
    fileNameFromPath(source.asset?.file_path) ??
    readString(provenance.origin)
  )
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function clampProgress(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function getProgressPercent(info: Record<string, unknown> | undefined): number | null {
  if (!info) return null

  const directProgress =
    readNumber(info.progress) ??
    readNumber(info.percentage) ??
    readNumber(info.percent)
  if (directProgress !== null) {
    return clampProgress(directProgress)
  }

  const processed =
    readNumber(info.processed) ??
    readNumber(info.processed_items) ??
    readNumber(info.completed)
  const total =
    readNumber(info.total) ??
    readNumber(info.total_items)

  if (processed === null || total === null || total <= 0) return null
  return clampProgress((processed / total) * 100)
}

export function SourceCard({
  source,
  onClick,
  onDelete,
  onRetry,
  onRemoveFromNotebook,
  onRefresh,
  className,
  showRemoveFromNotebook = false,
  showVisualCover,
  contextMode,
  onContextModeChange,
  notebookId,
}: SourceCardProps) {
  const { t } = useTranslation()
  const sourceVisualsEnabled = useSourceVisualsEnabled()
  const visualCoversEnabled = isVisualSystemV2Enabled() && sourceVisualsEnabled
  // v0.8.130 — Phase 2d: only when there is an image or a visual status to show; the
  // bare fallback just repeated the title above the row.
  const hasVisualContent = source.visual != null || source.visual_status != null
  const shouldShowVisualCover = visualCoversEnabled && (showVisualCover ?? true) && hasVisualContent
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const statusConfigMap = getStatusConfig(t)
  const resolvedNotebookId =
    notebookId ??
    ((source as SourceListResponse & { notebooks?: string[] }).notebooks &&
    (source as SourceListResponse & { notebooks?: string[] }).notebooks!.length > 0
      ? (source as SourceListResponse & { notebooks?: string[] }).notebooks![0]
      : null)
  
  // Only fetch status for sources that might have async processing
  const sourceWithStatus = source as SourceListResponse & { command_id?: string; status?: string }

  // Track processing state to continue polling until we detect completion
  const [wasProcessing, setWasProcessing] = useState(false)

  const shouldFetchStatus = !!sourceWithStatus.command_id ||
    sourceWithStatus.status === 'new' ||
    sourceWithStatus.status === 'queued' ||
    sourceWithStatus.status === 'running' ||
    wasProcessing // Keep polling if we were processing to catch the completion

  const { data: statusData, isLoading: statusLoading } = useSourceStatus(
    source.id,
    shouldFetchStatus
  )

  // Determine current status
  // If source has a command_id but no status, treat as "new" (just created)
  const rawStatus = statusData?.status || sourceWithStatus.status
  const currentStatus: SourceStatus = isSourceStatus(rawStatus)
    ? rawStatus
    : (sourceWithStatus.command_id ? 'new' : 'completed')


  // v0.7.56 — track the post-completion refresh timeout in a ref so
  // unmount + rapid status flips don't leak a setTimeout that fires
  // after the parent stopped caring. The previous bare `setTimeout`
  // had no cleanup: filter changes, page nav, or back-to-back status
  // flips queued multiple refreshes on a possibly-unmounted parent.
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const currentStatusFromData = statusData?.status || sourceWithStatus.status

    // If we're currently processing, mark that we were processing
    if (currentStatusFromData === 'new' || currentStatusFromData === 'running' || currentStatusFromData === 'queued') {
      setWasProcessing(true)
    }

    // If we were processing and now completed/failed, trigger refresh and stop polling
    if (wasProcessing &&
        (currentStatusFromData === 'completed' || currentStatusFromData === 'failed')) {
      setWasProcessing(false) // Stop polling

      if (onRefresh) {
        // Clear any previously queued refresh so rapid flips don't
        // pile up.
        if (refreshTimeoutRef.current) {
          clearTimeout(refreshTimeoutRef.current)
        }
        refreshTimeoutRef.current = setTimeout(() => {
          refreshTimeoutRef.current = null
          onRefresh()
        }, 500) // Small delay to ensure API is updated
      }
    }
  }, [statusData, sourceWithStatus.status, wasProcessing, onRefresh, source.id])

  // Cancel the pending refresh on unmount to avoid calling onRefresh
  // against a stale parent (and avoid React's "state update on
  // unmounted component" warnings on slow consumers).
  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
        refreshTimeoutRef.current = null
      }
    }
  }, [])
  
  const statusConfig = statusConfigMap[currentStatus] || statusConfigMap.completed
  const StatusIcon = statusConfig.icon
  const sourceType = getSourceType(source)
  const SourceTypeIcon = SOURCE_TYPE_ICONS[sourceType]
  
   const title = source.title || t('sources.untitledSource')

  const isProcessing: boolean = currentStatus === 'new' || currentStatus === 'running' || currentStatus === 'queued'
  const isFailed: boolean = currentStatus === 'failed'
  const isCompleted: boolean = currentStatus === 'completed'
  const isFileUnavailable = sourceType === 'upload' && source.file_available === false
  const hasNoExtractedText = isCompleted && source.extraction_quality === 'no_text'
  const hasLowExtractedText = isCompleted && source.extraction_quality === 'low_text'
  const canRetry = !isFileUnavailable
  const podcastDisabledReason = !isCompleted
    ? t('sources.sourceCard.podcastNeedsProcessing')
    : isFileUnavailable
      ? t('sources.sourceCard.podcastFileUnavailable')
      : hasNoExtractedText
        ? t('sources.sourceCard.podcastNoContent')
        : undefined
  const insightsPodcastDisabledReason = !isCompleted
    ? t('sources.sourceCard.insightsPodcastNeedsProcessing')
    : source.insights_count <= 0
      ? t('sources.sourceCard.insightsPodcastNone')
      : undefined
  const progressPercent = getProgressPercent(statusData?.processing_info ?? source.processing_info)
  const notebookCount = source.notebook_count ?? 0
  const isShared = source.is_shared || notebookCount > 1
  const provenanceLabel = getProvenanceLabel(source)

  const handleRetry = () => {
    if (onRetry && canRetry) {
      onRetry(source.id)
    }
  }

  const handleDelete = () => {
    if (onDelete) {
      onDelete(source.id)
    }
  }

  const handleRemoveFromNotebook = () => {
    if (onRemoveFromNotebook) {
      onRemoveFromNotebook(source.id)
    }
  }

  const handleCardClick = () => {
    if (onClick) {
      onClick(source.id)
    }
  }

  // v0.8.130 — Phase 2d: metadata as one quiet line of text (the pills wrapped a card to
  // ~110px). Each item stays its own element so it can be read and matched on its own.
  const metaItems: React.ReactNode[] = [
    !isCompleted && (
      <span key="status" className={cn('font-medium', statusConfig.color)}>
        {statusLoading && shouldFetchStatus ? t('sources.checking') : statusConfig.label}
      </span>
    ),
    <span key="type">{getSourceTypeLabel(sourceType, t)}</span>,
    isCompleted && source.insights_count > 0 && (
      <span key="insights">{t('sources.insightsCount').replace('{count}', source.insights_count.toString())}</span>
    ),
    isShared && <span key="shared">{notebookCount > 1 ? t('sources.sourceCard.sharedWithCount', { count: notebookCount }) : t('sources.sourceCard.shared')}</span>,
    provenanceLabel && <span key="provenance">{provenanceLabel}</span>,
    ...(isCompleted && source.topics ? source.topics.slice(0, 2).map((topic) => <span key={`topic-${topic}`}>{topic}</span>) : []),
    isCompleted && source.topics && source.topics.length > 2 && <span key="topics-more">+{source.topics.length - 2}</span>,
  ].filter(Boolean)
  const warnings = [
    isFileUnavailable && t('sources.fileUnavailable'),
    hasNoExtractedText && t('sources.noExtractedText'),
    hasLowExtractedText && t('sources.lowExtractedText'),
  ].filter((warning): warning is string => Boolean(warning))

  return (
    // v0.8.130 — Phase 2d: a flat row (NotebookLM's source list) instead of a bordered,
    // shadowed card. The context toggle leads the row, the actions float over its end on
    // hover (inline on touch screens), so a 20% column still has room for the title.
    <div
      data-dn-source-row=""
      className={cn(
        'group relative -mx-2 cursor-pointer rounded-lg px-2 py-1.5 transition-colors hover:bg-accent',
        className
      )}
      onClick={handleCardClick}
    >
      {shouldShowVisualCover && (
        <div className="mb-2">
          <SourceCover source={source} variant="compact" />
        </div>
      )}
      <div className="flex items-center gap-2">
        {onContextModeChange && contextMode ? (
          <ContextToggle
            mode={contextMode}
            hasInsights={source.insights_count > 0}
            onChange={onContextModeChange}
          />
        ) : (
          <span className="flex size-8 flex-none items-center justify-center text-muted-foreground">
            <SourceTypeIcon className="h-4 w-4" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          {/* v0.8.130 — Phase 4b: h3 under the column's h2 (h4 skipped a level). */}
          <h3
            className="truncate text-sm font-medium leading-5 transition-colors group-hover:text-primary"
            title={title}
          >
            {title}
          </h3>
          <p className="truncate text-xs leading-5 text-muted-foreground">
            {!isCompleted && (
              <StatusIcon className={cn('mr-1 inline h-3 w-3 align-[-2px]', statusConfig.color, isProcessing && 'animate-spin')} />
            )}
            {metaItems.map((item, index) => (
              <Fragment key={index}>
                {index > 0 && <span aria-hidden="true"> · </span>}
                {item}
              </Fragment>
            ))}
          </p>
          {warnings.map((warning) => (
            <p key={warning} className="flex items-center gap-1 text-xs leading-5 text-destructive-ink">
              <AlertTriangle className="h-3 w-3 flex-none" />
              <span>{warning}</span>
            </p>
          ))}
          {/* Processing message for active statuses */}
          {statusData?.message && (isProcessing || isFailed) && (
            <p className="text-xs italic text-muted-foreground">
              {statusData.message}
            </p>
          )}
          {/* v0.8.88 — auto-summary preview (opt-in source auto-summary). */}
          {isCompleted && source.summary_preview && (
            <p className="truncate text-xs italic text-muted-foreground">
              {source.summary_preview}
            </p>
          )}
        </div>

          {/* Actions: floats over the row's end on hover/focus; inline where hover is unavailable */}
          <div className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:static [@media(hover:none)]:translate-y-0 [@media(hover:none)]:opacity-100">
            {/* Actions dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t('sources.sourceCard.sourceActions')}
                  className="h-8 w-8 rounded-md bg-card p-0 shadow-xs"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {showRemoveFromNotebook && (
                <>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      handleRemoveFromNotebook()
                    }}
                    disabled={!onRemoveFromNotebook}
                  >
                    <Unlink className="h-4 w-4 mr-2" />
                    {t('sources.removeFromNotebook')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}

              {isFailed && (
                <>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      handleRetry()
                    }}
                    disabled={!onRetry || !canRetry}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    {t('sources.retryProcessing')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}

              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  openPodcastReview(
                    [{ kind: 'app_source', sourceId: source.id, inclusionMode: 'full' }],
                    'quick',
                    resolvedNotebookId
                  )
                }}
                disabled={Boolean(podcastDisabledReason)}
              >
                <Podcast className="h-4 w-4 mr-2" />
                {podcastDisabledReason
                  ? t('sources.sourceCard.turnIntoPodcastDisabled', { reason: podcastDisabledReason })
                  : t('sources.sourceCard.turnIntoPodcast')}
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  openPodcastReview(
                    [{ kind: 'app_source', sourceId: source.id, inclusionMode: 'insights' }],
                    'quick',
                    resolvedNotebookId
                  )
                }}
                disabled={Boolean(insightsPodcastDisabledReason)}
              >
                <Podcast className="h-4 w-4 mr-2" />
                {insightsPodcastDisabledReason
                  ? t('sources.sourceCard.turnInsightsIntoPodcastDisabled', { reason: insightsPodcastDisabledReason })
                  : t('sources.sourceCard.turnInsightsIntoPodcast')}
              </DropdownMenuItem>

              <DropdownMenuSeparator />

              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  handleDelete()
                }}
                disabled={!onDelete}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {t('sources.deleteSource')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        </div>
        {isFailed && (
          <div className="flex gap-2 pt-1.5 pl-10">
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                handleRetry()
              }}
              disabled={!onRetry || !canRetry}
              className="h-7 text-xs"
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              {t('sources.retry')}
            </Button>
          </div>
        )}

        {/* Processing progress indicator */}
        {isProcessing && progressPercent !== null && (
          <div className="mt-1.5 pl-10">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-muted-foreground">{t('common.progress')}</span>
              <span className="text-xs text-muted-foreground">
                {Math.round(progressPercent)}%
              </span>
            </div>
            <Progress value={progressPercent} className="h-1.5" />
          </div>
        )}
    </div>
  )
}
