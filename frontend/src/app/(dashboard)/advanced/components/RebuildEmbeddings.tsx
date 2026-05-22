'use client'

import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import { Loader2, AlertCircle, AlertTriangle, CheckCircle2, XCircle, Clock } from 'lucide-react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { embeddingApi } from '@/lib/api/embedding'
import type { RebuildEmbeddingsRequest, RebuildStatusResponse } from '@/lib/api/embedding'
import { useTranslation } from '@/lib/hooks/use-translation'

export function RebuildEmbeddings() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'existing' | 'all'>('existing')
  const [includeSources, setIncludeSources] = useState(true)
  const [includeNotes, setIncludeNotes] = useState(true)
  const [includeInsights, setIncludeInsights] = useState(true)
  const [commandId, setCommandId] = useState<string | null>(null)
  const [status, setStatus] = useState<RebuildStatusResponse | null>(null)
  // v0.7.158 — `pollingInterval` was previously a `useState` value that
  // `stopPolling` closed over. Because `stopPolling` was wrapped in
  // useCallback(..., [pollingInterval]), the unmount cleanup
  // useEffect(() => () => stopPolling(), [stopPolling]) re-ran on
  // EVERY setPollingInterval(...) — and the prior unmount callback
  // closed over a STALE pollingInterval (often null because the state
  // hadn't propagated yet). Result: an orphaned setInterval kept
  // hitting /embedding/rebuild/status forever after the user
  // navigated away from /advanced. Refactored to useRef so the
  // current interval is always readable from cleanup without
  // triggering re-renders or stale closures.
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Rebuild mutation
  const rebuildMutation = useMutation({
    mutationFn: async (request: RebuildEmbeddingsRequest) => {
      return embeddingApi.rebuildEmbeddings(request)
    },
    onSuccess: (data) => {
      setCommandId(data.command_id)
      // Start polling for status
      startPolling(data.command_id)
    }
  })

  // Start polling for rebuild status
  // v0.7.158 — reads/writes pollingIntervalRef.current instead of
  // state, so a re-render doesn't drop the live interval id.
  const startPolling = (cmdId: string) => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
    }

    const interval = setInterval(async () => {
      try {
        const statusData = await embeddingApi.getRebuildStatus(cmdId)
        setStatus(statusData)

        // Stop polling if completed or failed
        if (statusData.status === 'completed' || statusData.status === 'failed') {
          stopPolling()
        }
      } catch (error) {
        console.error('Failed to fetch rebuild status:', error)
      }
    }, 5000) // Poll every 5 seconds

    pollingIntervalRef.current = interval
  }

  // Stop polling
  // v0.7.158 — no longer wrapped in useCallback (ref is stable, no
  // dependency to track), eliminating the stale-closure cleanup bug
  // where the unmount callback closed over an outdated interval id.
  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }

  // Cleanup on unmount
  // v0.7.158 — empty dep array. Reads ref at unmount time, so we
  // ALWAYS see the current interval (whatever it was set to last).
  // The previous [stopPolling] dep caused the cleanup to re-arm on
  // every state change, with each re-armed callback closing over a
  // stale pollingInterval — orphaning the interval after unmount.
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [])

  const handleStartRebuild = () => {
    const request: RebuildEmbeddingsRequest = {
      mode,
      include_sources: includeSources,
      include_notes: includeNotes,
      include_insights: includeInsights
    }

    rebuildMutation.mutate(request)
  }

  const handleReset = () => {
    stopPolling()
    setCommandId(null)
    setStatus(null)
    rebuildMutation.reset()
  }

  const isAnyTypeSelected = includeSources || includeNotes || includeInsights
  const isRebuildActive = commandId && status && (status.status === 'queued' || status.status === 'running')

  const progressData = status?.progress
  const stats = status?.stats

  const totalItems = progressData?.total_items ?? progressData?.total ?? 0
  const processedItems = progressData?.processed_items ?? progressData?.processed ?? 0
  const derivedProgressPercent = progressData?.percentage ?? (totalItems > 0 ? (processedItems / totalItems) * 100 : 0)
  const progressPercent = Number.isFinite(derivedProgressPercent) ? derivedProgressPercent : 0

  const sourcesProcessed = stats?.sources_processed ?? stats?.sources ?? 0
  const notesProcessed = stats?.notes_processed ?? stats?.notes ?? 0
  const insightsProcessed = stats?.insights_processed ?? stats?.insights ?? 0
  const failedItems = stats?.failed_items ?? stats?.failed ?? 0

  const computedDuration = status?.started_at && status?.completed_at
    ? (new Date(status.completed_at).getTime() - new Date(status.started_at).getTime()) / 1000
    : undefined
  const processingTimeSeconds = stats?.processing_time ?? computedDuration

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {t('advanced.rebuildEmbeddings')}
        </CardTitle>
        <CardDescription>
          {t('advanced.rebuildEmbeddingsDesc')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Configuration Form */}
        {!isRebuildActive && (
          <div className="space-y-6">
            <div className="space-y-3">
              <Label htmlFor="mode">{t('advanced.rebuild.mode')}</Label>
              <Select value={mode} onValueChange={(value) => setMode(value as 'existing' | 'all')}>
                <SelectTrigger id="mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="existing">{t('advanced.rebuild.existing')}</SelectItem>
                  <SelectItem value="all">{t('advanced.rebuild.all')}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                {mode === 'existing'
                  ? t('advanced.rebuild.existingDesc')
                  : t('advanced.rebuild.allDesc')}
              </p>
            </div>

            <div className="space-y-3" role="group" aria-labelledby="include-label">
              <span id="include-label" className="text-sm font-medium leading-none">{t('advanced.rebuild.include')}</span>
              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="sources"
                    checked={includeSources}
                    onCheckedChange={(checked) => setIncludeSources(checked === true)}
                  />
                  <Label htmlFor="sources" className="font-normal cursor-pointer">
                    {t('navigation.sources')}
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="notes"
                    checked={includeNotes}
                    onCheckedChange={(checked) => setIncludeNotes(checked === true)}
                  />
                  <Label htmlFor="notes" className="font-normal cursor-pointer">
                    {t('common.notes')}
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="insights"
                    checked={includeInsights}
                    onCheckedChange={(checked) => setIncludeInsights(checked === true)}
                  />
                  <Label htmlFor="insights" className="font-normal cursor-pointer">
                    {t('common.insights')}
                  </Label>
                </div>
              </div>
              {!isAnyTypeSelected && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {t('advanced.rebuild.selectOneError')}
                  </AlertDescription>
                </Alert>
              )}
            </div>

            <Button
              onClick={handleStartRebuild}
              disabled={!isAnyTypeSelected || rebuildMutation.isPending}
              className="w-full"
            >
              {rebuildMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('advanced.rebuild.starting')}
                </>
              ) : (
                t('advanced.rebuild.startBtn')
              )}
            </Button>

            {rebuildMutation.isError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {t('advanced.rebuild.failed')}: {(rebuildMutation.error as Error)?.message || t('common.error')}
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Status Display */}
        {status && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {status.status === 'queued' && <Clock className="h-5 w-5 text-yellow-500" />}
                {status.status === 'running' && <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />}
                {status.status === 'completed' && <CheckCircle2 className="h-5 w-5 text-green-500" />}
                {/* v0.7.180 — Only the failed-status icon swaps to the
                    theme token (text-red-500 → text-destructive). The
                    queued/running/completed icons keep their semantic
                    palette per user constraint "no theme color changes" —
                    only the destructive case has a canonical theme token
                    that lights up correctly in dark + alt themes. */}
                {status.status === 'failed' && <XCircle className="h-5 w-5 text-destructive" />}
                <div className="flex flex-col">
                  <span className="font-medium">
                    {status.status === 'queued' && t('advanced.rebuild.queued')}
                    {status.status === 'running' && t('advanced.rebuild.running')}
                    {status.status === 'completed' && t('advanced.rebuild.completed')}
                    {status.status === 'failed' && t('advanced.rebuild.failed')}
                  </span>
                  {status.status === 'running' && (
                    <span className="text-sm text-muted-foreground">
                      {t('advanced.rebuild.leavePageHint')}
                    </span>
                  )}
                </div>
              </div>
              {(status.status === 'completed' || status.status === 'failed') && (
                <Button variant="outline" size="sm" onClick={handleReset}>
                  {t('advanced.rebuild.startNew')}
                </Button>
              )}
            </div>

            {progressData && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{t('common.progress')}</span>
                  <span className="font-medium">
                    {t('advanced.rebuild.itemsProcessed')
                      .replace('{processed}', processedItems.toString())
                      .replace('{total}', totalItems.toString())
                      .replace('{percent}', progressPercent.toFixed(1))}
                  </span>
                </div>
                <Progress value={progressPercent} className="h-2" />
                {failedItems > 0 && (
                  // v0.7.167 — raw `⚠️` emoji replaced with the lucide
                  // AlertTriangle icon used everywhere else in the app.
                  // The previous emoji was the only icon-via-Unicode in
                  // an otherwise lucide-driven UI; jarring next to the
                  // sibling AlertCircle just below at line 323.
                  <p className="text-sm text-yellow-600 inline-flex items-center gap-1.5">
                    <AlertTriangle className="h-4 w-4" />
                    {t('advanced.rebuild.failedItems').replace('{count}', failedItems.toString())}
                  </p>
                )}
              </div>
            )}

            {/* v0.7.167 — Stats grid: number weights toned down from
                `text-2xl font-bold` (read as "marketing dashboard") to
                `text-xl font-semibold` (reads as "settings"). The
                surrounding Advanced page is a settings screen; the
                stats shouldn't out-weigh the page H1. Also bumped the
                `grid-cols-4` to be responsive — `sm:grid-cols-2
                lg:grid-cols-4` so 4 cramped tiles don't collide on
                narrow viewports. */}
            {stats && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">{t('navigation.sources')}</p>
                  <p className="text-xl font-semibold">{sourcesProcessed}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">{t('common.notes')}</p>
                  <p className="text-xl font-semibold">{notesProcessed}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">{t('common.insights')}</p>
                  <p className="text-xl font-semibold">{insightsProcessed}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">{t('advanced.rebuild.time')}</p>
                  <p className="text-xl font-semibold">
                    {processingTimeSeconds !== undefined ? `${processingTimeSeconds.toFixed(1)}s` : '—'}
                  </p>
                </div>
              </div>
            )}

            {status.error_message && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{status.error_message}</AlertDescription>
              </Alert>
            )}

            {status.started_at && (
              <div className="text-sm text-muted-foreground space-y-1">
                <p>{t('common.created').replace('{time}', new Date(status.started_at).toLocaleString())}</p>
                {status.completed_at && (
                  <p>{t('notebooks.updated')}: {new Date(status.completed_at).toLocaleString()}</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Help Section */}
         <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="when">
            <AccordionTrigger>{t('advanced.rebuild.whenToRebuild')}</AccordionTrigger>
            <AccordionContent className="space-y-2 text-sm">
              <p>{t('advanced.rebuild.whenToRebuildAns')}</p>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="time">
            <AccordionTrigger>{t('advanced.rebuild.howLong')}</AccordionTrigger>
            <AccordionContent className="space-y-2 text-sm">
              <p>{t('advanced.rebuild.howLongAns')}</p>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="safe">
            <AccordionTrigger>{t('advanced.rebuild.isSafe')}</AccordionTrigger>
            <AccordionContent className="space-y-2 text-sm">
              <p>{t('advanced.rebuild.isSafeAns')}</p>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  )
}
