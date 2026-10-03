'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'
import { ACTIVE_EPISODE_STATUSES, FAILED_EPISODE_STATUSES, type PodcastEpisode } from '@/lib/types/podcasts'
import { SyncedTranscript } from './SyncedTranscript'

const PHASE_3_LOCK_COPY_KEY = 'podcasts.episodeLab.lockedStageCopy'
// v0.8.130 — was 'Source citation — claim evidence mapping arrives in Phase 3'; internal phase
// labels are not user-facing copy.
const CLAIM_CITATION_UNAVAILABLE_COPY_KEY = 'podcasts.episodeLab.claimCitationUnavailable'
const SOURCE_CITATION_ID = /^source:[A-Za-z0-9_-]{1,121}$/

/** `labelKey` is an i18n key; translate with t() where it renders. */
export interface EpisodeStageHistoryEntry {
  labelKey: string
  current: boolean
}

type OutlineSegmentValue = {
  name?: unknown
  title?: unknown
  description?: unknown
  size?: unknown
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function outlineSegments(episode: PodcastEpisode): OutlineSegmentValue[] {
  const raw = episode.outline
  if (!raw || typeof raw !== 'object' || !Array.isArray(raw.segments)) return []
  return raw.segments.filter((segment): segment is OutlineSegmentValue => Boolean(segment && typeof segment === 'object'))
}

function hasTranscript(episode: PodcastEpisode): boolean {
  if ((episode.transcript_segments?.length ?? 0) > 0) return true
  const transcript = episode.transcript
  return Boolean(transcript && typeof transcript === 'object' && Array.isArray(transcript.transcript) && transcript.transcript.length > 0)
}

function activeGenerationLabel(stage: string): string | null {
  if (stage === 'generating_outline') return 'podcasts.episodeLab.stage.generatingOutline'
  if (stage === 'generating_transcript') return 'podcasts.episodeLab.stage.generatingTranscript'
  if (stage === 'generating_audio' || stage === 'combining_audio') return 'podcasts.episodeLab.stage.generatingAudio'
  return null
}

/**
 * Build history from fields persisted on the episode. No timestamps or
 * unrecorded evidence states are inferred here.
 */
export function getEpisodeStageHistory(episode: PodcastEpisode): EpisodeStageHistoryEntry[] {
  const history: EpisodeStageHistoryEntry[] = [{ labelKey: 'podcasts.episodeLab.stage.created', current: false }]
  const segments = outlineSegments(episode)
  const hasOutline = segments.length > 0
  const transcriptPresent = hasTranscript(episode)
  const audioPresent = Boolean(episode.audio_url ?? episode.audio_file)
  const stage = (episode.generation_stage ?? '').toLowerCase()
  const status = (episode.job_status ?? '').toLowerCase()
  const failed = status === 'failed' || status === 'error' || stage === 'failed' || stage === 'error'
  const cancelled = status === 'cancelled' || status === 'canceled' || stage === 'cancelled' || stage === 'canceled'
  const terminal = failed ? 'podcasts.episodeLab.stage.failed' : cancelled ? 'podcasts.episodeLab.stage.cancelled' : status === 'completed' ? 'podcasts.episodeLab.stage.completed' : null
  const generationLabelKey = activeGenerationLabel(stage)

  if (hasOutline) history.push({ labelKey: 'podcasts.episodeLab.stage.outlinePresent', current: false })
  if (stage === 'awaiting_review') history.push({ labelKey: 'podcasts.episodeLab.stage.awaitingOutlineReview', current: false })
  if (transcriptPresent) history.push({ labelKey: 'podcasts.episodeLab.stage.transcriptPresent', current: false })
  if (audioPresent) history.push({ labelKey: 'podcasts.episodeLab.stage.audioPresent', current: false })
  if (generationLabelKey) history.push({ labelKey: generationLabelKey, current: false })

  // Awaiting review and an active generation are not terminal completion.
  // A persisted failure/cancellation always wins over any stale active stage.
  if (terminal && !(!failed && !cancelled && (stage === 'awaiting_review' || generationLabelKey))) {
    history.push({ labelKey: terminal, current: false })
  }

  const currentLabelKey = failed || cancelled
    ? terminal
    : stage === 'awaiting_review'
      ? 'podcasts.episodeLab.stage.awaitingOutlineReview'
      : generationLabelKey
        ?? (terminal ?? (audioPresent ? 'podcasts.episodeLab.stage.audioPresent' : transcriptPresent ? 'podcasts.episodeLab.stage.transcriptPresent' : hasOutline ? 'podcasts.episodeLab.stage.outlinePresent' : 'podcasts.episodeLab.stage.created'))
  const current = history.find((entry) => entry.labelKey === currentLabelKey)
  if (current) current.current = true

  return history
}

/** Existing API-relative audio only; raw worker paths and remote URLs stay UI-inert. */
export function isContainedAudioDownloadUrl(value: string | null | undefined): value is string {
  return Boolean(value && /^\/api\/podcasts\/episodes\/[A-Za-z0-9:_-]{1,160}\/audio$/.test(value))
}

export function isExactSourceCitationId(value: string): boolean {
  return SOURCE_CITATION_ID.test(value)
}

interface EpisodeLabProps {
  episode: PodcastEpisode
  onClose: () => void
  onRetry?: (episodeId: string) => Promise<void> | void
  onCancel?: (episodeId: string) => Promise<void> | void
  onCitationClick?: (citationId: string) => void
  retrying?: boolean
}

/**
 * A route-level episode workspace. It hands playback to the app-shell player
 * so progress survives navigation, while keeping citation links honest until
 * the evidence graph can resolve a stable claim target.
 */
export function EpisodeLab({ episode, onClose, onRetry, onCancel, onCitationClick, retrying = false }: EpisodeLabProps) {
  const { t } = useTranslation()
  const setPlayingEpisode = useAudioPlayerStore((state) => state.setEpisode)
  const setPosition = useAudioPlayerStore((state) => state.setPosition)
  const currentTime = useAudioPlayerStore((state) => state.positionByEpisode[episode.id] ?? 0)
  const [citationNotice, setCitationNotice] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<'retry' | 'cancel' | null>(null)
  const audioPath = episode.audio_url ?? episode.audio_file
  const downloadUrl = isContainedAudioDownloadUrl(episode.audio_url) ? episode.audio_url : null
  const canRetry = FAILED_EPISODE_STATUSES.includes(episode.job_status ?? 'unknown')
  const canCancel = ACTIVE_EPISODE_STATUSES.includes(episode.job_status ?? 'unknown')
    && episode.generation_stage !== 'awaiting_review'
  const history = getEpisodeStageHistory(episode)
  const segments = outlineSegments(episode)
  const retryPending = pendingAction === 'retry' || retrying
  const actionsPending = pendingAction !== null || retrying

  const playInGlobalPlayer = () => {
    if (!audioPath) return
    setPlayingEpisode({
      id: episode.id,
      title: episode.name,
      sourcePath: audioPath,
      transcriptSegments: episode.transcript_segments ?? [],
    })
  }

  const seek = (seconds: number) => {
    setPosition(episode.id, seconds)
  }

  const handleCitationClick = (citationId: string) => {
    if (onCitationClick && isExactSourceCitationId(citationId)) {
      onCitationClick(citationId)
      return
    }
    setCitationNotice(CLAIM_CITATION_UNAVAILABLE_COPY_KEY)
  }

  const runEpisodeAction = (action: 'retry' | 'cancel', callback: ((episodeId: string) => Promise<void> | void) | undefined) => {
    if (!callback || actionsPending) return
    setPendingAction(action)
    try {
      void Promise.resolve(callback(episode.id)).finally(() => setPendingAction(null))
    } catch {
      setPendingAction(null)
    }
  }

  return (
    <section aria-label={t('podcasts.episodeLab.title')} className="space-y-4 rounded-md border bg-card p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t('podcasts.episodeLab.title')}</h2>
          <p className="text-sm text-muted-foreground">{episode.name}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>{t('podcasts.episodeLab.close')}</Button>
      </header>

      <section aria-labelledby="episode-lab-outline" className="rounded border p-3">
        <h3 id="episode-lab-outline" className="font-medium">{t('podcasts.episodeLab.currentOutline')}</h3>
        {segments.length > 0 ? (
          <ol className="mt-2 space-y-2">
            {segments.map((segment, index) => {
              const name = stringValue(segment.name) ?? stringValue(segment.title) ?? t('podcasts.episodeLab.segmentFallback', { number: index + 1 })
              const description = stringValue(segment.description)
              const size = stringValue(segment.size)
              return (
                <li key={`${name}-${index}`} className="rounded border bg-muted/20 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">{name}</p>
                    {size ? <span className="rounded border px-2 py-0.5 text-xs uppercase tracking-wide">{size}</span> : null}
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{description ?? t('podcasts.episodeLab.segmentDescriptionUnavailable')}</p>
                </li>
              )
            })}
          </ol>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">{t('podcasts.episodeLab.noOutline')}</p>
        )}
      </section>

      <section aria-labelledby="episode-lab-stage-history" className="rounded border p-3">
        <h3 id="episode-lab-stage-history" className="font-medium">{t('podcasts.episodeLab.stageHistory')}</h3>
        <ol className="mt-2 flex flex-wrap gap-2 text-sm">
          {history.map((entry) => (
            <li key={entry.labelKey} aria-current={entry.current ? 'step' : undefined} className={entry.current ? 'rounded bg-muted px-2 py-1' : 'rounded border px-2 py-1'}>
              {t(entry.labelKey)}
            </li>
          ))}
          <li className="rounded border border-dashed px-2 py-1 text-muted-foreground">
            <span aria-disabled="true"><span className="font-medium">{t('podcasts.episodeLab.evidence')}</span> — <span>{t(PHASE_3_LOCK_COPY_KEY)}</span></span>
          </li>
          <li className="rounded border border-dashed px-2 py-1 text-muted-foreground">
            <span aria-disabled="true"><span className="font-medium">{t('podcasts.episodeLab.verification')}</span> — <span>{t(PHASE_3_LOCK_COPY_KEY)}</span></span>
          </li>
        </ol>
      </section>

      <section aria-labelledby="episode-lab-audio" className="rounded border p-3">
        <h3 id="episode-lab-audio" className="font-medium">{t('podcasts.episodeLab.audioAndTranscript')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('podcasts.episodeLab.playbackNotice')}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={playInGlobalPlayer} disabled={!audioPath}>{t('podcasts.episodeLab.playInGlobalPlayer')}</Button>
          {downloadUrl ? <Button asChild type="button" size="sm" variant="outline"><a href={downloadUrl} download>{t('podcasts.episodeLab.downloadAudio')}</a></Button> : <Button type="button" size="sm" variant="outline" disabled>{t('podcasts.episodeLab.downloadAudio')}</Button>}
        </div>
        <div className="mt-3">
          <SyncedTranscript
            segments={episode.transcript_segments ?? []}
            currentTime={currentTime}
            onSeek={seek}
            onCitationClick={handleCitationClick}
          />
          {citationNotice ? <p role="status" className="mt-2 text-sm text-muted-foreground">{t(citationNotice)}</p> : null}
        </div>
      </section>

      {(canRetry && onRetry) || (canCancel && onCancel) ? <section aria-label={t('podcasts.episodeLab.episodeActions')} className="flex flex-wrap gap-2">
        {canRetry && onRetry ? <Button type="button" size="sm" variant="outline" onClick={() => runEpisodeAction('retry', onRetry)} disabled={actionsPending} aria-busy={retryPending}>{retryPending ? t('podcasts.episodeLab.retrying') : t('podcasts.episodeLab.retry')}</Button> : null}
        {canCancel && onCancel ? <Button type="button" size="sm" variant="outline" onClick={() => runEpisodeAction('cancel', onCancel)} disabled={actionsPending} aria-busy={pendingAction === 'cancel'}>{pendingAction === 'cancel' ? t('podcasts.episodeLab.cancelling') : t('podcasts.episodeLab.cancel')}</Button> : null}
      </section> : null}
    </section>
  )
}
