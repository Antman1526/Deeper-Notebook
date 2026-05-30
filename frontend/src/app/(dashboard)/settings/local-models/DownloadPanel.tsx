'use client'

/**
 * DownloadPanel.tsx — v0.8.39b
 *
 * Curated HuggingFace GGUF recommendations + per-row download with
 * live progress. Companion to the inventory table on the same page.
 *
 * Flow:
 *   1. GET /local-models/recommendations populates the cards.
 *   2. Click "Download" → POST /local-models/download (returns job_id).
 *   3. Poll /local-models/downloads/{job_id} every 1s while
 *      status in ('queued', 'downloading').
 *   4. On 'completed', invalidate the inventory query so the new model
 *      appears in the table without manual refresh.
 *   5. On 'failed', surface the error inline; retry button re-POSTs.
 *
 * Out of scope this iteration:
 *   - Persistent job state across API restart (deferred to v0.8.39d
 *     SurrealDB-backed registry).
 *   - Cancel button (the underlying task isn't cancellable today;
 *     deferred along with the persistent registry).
 */

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Download,
  CheckCircle2,
  XCircle,
  Loader2,
  X,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import apiClient from '@/lib/api/client'
import { useTranslation } from '@/lib/hooks/use-translation'

export type Recommendation = {
  id: string
  label: string
  description: string
  repo_id: string
  filename: string
  approx_size_gb: number
  tags: string[]
  context_length: number
}

type RecommendationsResponse = {
  recommendations: Recommendation[]
}

type DownloadJob = {
  job_id: string
  // v0.8.39e — "cancelled" added as a terminal state.
  status: 'queued' | 'downloading' | 'completed' | 'failed' | 'cancelled'
  repo_id: string
  filename: string
  target_path: string
  bytes_downloaded: number
  bytes_total: number
  error: string | null
}

type StartDownloadResponse = Omit<DownloadJob, 'repo_id' | 'filename' | 'error'>

function fmtGb(n: number): string {
  if (n < 1) return `${Math.round(n * 1000)} MB`
  return `${n.toFixed(1)} GB`
}

function pct(job: DownloadJob): number | null {
  if (!job.bytes_total) return null
  return Math.min(100, Math.round((job.bytes_downloaded / job.bytes_total) * 100))
}

function RecommendationCard({
  rec,
  jobByKey,
  onDownload,
  onCancel,
}: {
  rec: Recommendation
  jobByKey: Record<string, DownloadJob>
  onDownload: (rec: Recommendation) => void
  onCancel: (job: DownloadJob) => void
}) {
  const { t } = useTranslation()
  const key = `${rec.repo_id}::${rec.filename}`
  const job = jobByKey[key]
  const isActive = job && (job.status === 'queued' || job.status === 'downloading')
  const isDone = job?.status === 'completed'
  const isFailed = job?.status === 'failed'
  // v0.8.39e — surface cancelled as a distinct state so the user sees
  // "Resume" instead of "Retry" (semantically meaningful since the
  // .part file is on disk and the next click will resume from offset).
  const isCancelled = job?.status === 'cancelled'

  return (
    <Card data-testid={`recommendation-${rec.id}`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="space-y-1 flex-1 min-w-0">
            <CardTitle className="text-base font-medium">{rec.label}</CardTitle>
            <CardDescription className="text-xs">
              {rec.description}
            </CardDescription>
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            {rec.tags.map(tag => (
              <Badge
                key={tag}
                variant={tag === 'recommended' ? 'default' : 'secondary'}
                className="text-[10px]"
              >
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        <dl className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <dt className="text-muted-foreground">
              {t('localModels.colSize', { defaultValue: 'Size' })}
            </dt>
            <dd className="font-mono">~{fmtGb(rec.approx_size_gb)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">
              {t('localModels.colContext', { defaultValue: 'Context' })}
            </dt>
            <dd className="font-mono">
              {rec.context_length >= 1024
                ? `${Math.round(rec.context_length / 1024)}k`
                : rec.context_length}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">
              {t('localModels.colRepo', { defaultValue: 'Repo' })}
            </dt>
            <dd className="text-[10px] font-mono break-all">{rec.repo_id}</dd>
          </div>
        </dl>

        {isActive && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                {job.status === 'queued'
                  ? t('localModels.queued', { defaultValue: 'Queued…' })
                  : t('localModels.downloading', { defaultValue: 'Downloading…' })}
              </span>
              <span className="font-mono text-muted-foreground">
                {pct(job) !== null ? `${pct(job)}%` : '—'}
              </span>
            </div>
            <Progress value={pct(job) ?? undefined} />
            {/* v0.8.39e — Cancel button on in-flight downloads. Sets
                the cancel flag; the stream loop tears down on next
                chunk boundary. .part file stays on disk so a
                subsequent click can resume from offset. */}
            <div className="flex justify-end pt-1">
              <Button
                size="sm"
                variant="ghost"
                className="gap-1 h-6 text-xs"
                onClick={() => onCancel(job)}
                data-testid={`cancel-${rec.id}`}
              >
                <X className="h-3 w-3" />
                {t('localModels.cancel', { defaultValue: 'Cancel' })}
              </Button>
            </div>
          </div>
        )}

        {isCancelled && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <XCircle className="h-3 w-3" />
            {t('localModels.cancelled', {
              defaultValue: 'Cancelled. Click Resume to continue from where it stopped.',
            })}
          </div>
        )}

        {isDone && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3 w-3" />
            {t('localModels.completed', { defaultValue: 'Installed' })}
          </div>
        )}

        {isFailed && (
          <div className="flex items-start gap-1.5 text-xs text-destructive">
            <XCircle className="h-3 w-3 mt-0.5 shrink-0" />
            <span>
              {t('localModels.failed', {
                defaultValue: 'Download failed: {{error}}',
                error: job.error ?? 'unknown error',
              })}
            </span>
          </div>
        )}

        {!isActive && !isDone && (
          <Button
            size="sm"
            onClick={() => onDownload(rec)}
            data-testid={`download-${rec.id}`}
            className="gap-1.5"
          >
            <Download className="h-3 w-3" />
            {isCancelled
              ? t('localModels.resume', { defaultValue: 'Resume' })
              : isFailed
                ? t('localModels.retry', { defaultValue: 'Retry' })
                : t('localModels.download', { defaultValue: 'Download' })}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

export function DownloadPanel() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // Local map of (repo+filename) → job so re-polling can find the
  // right job even after a page navigation refetch.
  const [jobByKey, setJobByKey] = React.useState<Record<string, DownloadJob>>({})

  const { data, isLoading } = useQuery<RecommendationsResponse>({
    queryKey: ['local-models', 'recommendations'],
    queryFn: async () => {
      const resp = await apiClient.get<RecommendationsResponse>(
        '/local-models/recommendations',
      )
      return resp.data
    },
    staleTime: Infinity,
  })

  // v0.8.39d — On mount, reconcile + list any interrupted downloads
  // (the backend rebuilds them from on-disk .part.meta sidecars as
  // "cancelled"/resumable jobs after an API restart). Seed `jobByKey`
  // so a matching recommendation card shows the "Resume" button
  // proactively, instead of the user having to rediscover which model
  // was mid-download.
  const { data: listed } = useQuery<{ downloads: DownloadJob[] }>({
    queryKey: ['local-models', 'downloads'],
    queryFn: async () => {
      const resp = await apiClient.get<{ downloads: DownloadJob[] }>(
        '/local-models/downloads',
      )
      return resp.data
    },
    // One-shot on mount is enough — the per-job 1s poll below takes
    // over for anything in-flight. Refetch on focus so returning to
    // the tab after a restart surfaces newly-reconciled jobs.
    staleTime: 30_000,
  })
  React.useEffect(() => {
    if (!listed?.downloads?.length) return
    setJobByKey(prev => {
      const next = { ...prev }
      for (const job of listed.downloads) {
        const key = `${job.repo_id}::${job.filename}`
        // Don't clobber a job we're already actively tracking (the
        // per-job poll holds fresher state than this mount-time list).
        if (!next[key]) next[key] = job
      }
      return next
    })
  }, [listed])

  // Poll any in-flight job every 1s until terminal.
  React.useEffect(() => {
    const active = Object.values(jobByKey).filter(
      j => j.status === 'queued' || j.status === 'downloading',
    )
    if (active.length === 0) return
    const id = setInterval(async () => {
      for (const job of active) {
        try {
          const resp = await apiClient.get<DownloadJob>(
            `/local-models/downloads/${job.job_id}`,
          )
          const key = `${resp.data.repo_id}::${resp.data.filename}`
          setJobByKey(prev => ({ ...prev, [key]: resp.data }))
          if (resp.data.status === 'completed') {
            // Refresh inventory so the new model lands in the table.
            queryClient.invalidateQueries({
              queryKey: ['local-models', 'inventory'],
            })
          }
        } catch {
          // Transient 5xx — keep polling, the next tick may succeed.
        }
      }
    }, 1000)
    return () => clearInterval(id)
  }, [jobByKey, queryClient])

  const startMutation = useMutation({
    mutationFn: async (rec: Recommendation) => {
      const resp = await apiClient.post<StartDownloadResponse>(
        '/local-models/download',
        { repo_id: rec.repo_id, filename: rec.filename },
      )
      return { rec, ...resp.data }
    },
    onSuccess: data => {
      const key = `${data.rec.repo_id}::${data.rec.filename}`
      setJobByKey(prev => ({
        ...prev,
        [key]: {
          job_id: data.job_id,
          status: data.status,
          repo_id: data.rec.repo_id,
          filename: data.rec.filename,
          target_path: data.target_path,
          bytes_downloaded: data.bytes_downloaded,
          bytes_total: data.bytes_total,
          error: null,
        },
      }))
    },
  })

  // v0.8.39e — cancel mutation. Fires POST /downloads/{id}/cancel; the
  // polling loop above picks up the status="cancelled" transition on
  // the next tick and the card swaps to the "Resume" affordance.
  const cancelMutation = useMutation({
    mutationFn: async (job: DownloadJob) => {
      await apiClient.post<{ ok: boolean; detail: string }>(
        `/local-models/downloads/${job.job_id}/cancel`,
      )
      return job
    },
  })

  if (isLoading || !data) return null

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Download className="h-4 w-4" />
          {t('localModels.downloadHeader', {
            defaultValue: 'Download a model',
          })}
        </h2>
        <p className="text-xs text-muted-foreground">
          {t('localModels.downloadSubheader', {
            defaultValue:
              'Curated, known-good GGUFs from HuggingFace. One-click install into the local model directory.',
          })}
        </p>
      </header>
      <div className="space-y-3" data-testid="recommendations-list">
        {data.recommendations.map(rec => (
          <RecommendationCard
            key={rec.id}
            rec={rec}
            jobByKey={jobByKey}
            onDownload={r => startMutation.mutate(r)}
            onCancel={j => cancelMutation.mutate(j)}
          />
        ))}
      </div>
    </section>
  )
}

export default DownloadPanel
