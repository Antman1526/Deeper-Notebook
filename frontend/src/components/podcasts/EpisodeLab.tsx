'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'
import { ACTIVE_EPISODE_STATUSES, FAILED_EPISODE_STATUSES, type PodcastEpisode } from '@/lib/types/podcasts'
import { SyncedTranscript } from './SyncedTranscript'

interface EpisodeLabProps {
  episode: PodcastEpisode
  onClose: () => void
  onRetry?: (episodeId: string) => void
  onCancel?: (episodeId: string) => void
}

function stageLabel(episode: PodcastEpisode): string {
  if (episode.generation_stage === 'awaiting_review') return 'Awaiting outline review'
  if (episode.generation_stage) return episode.generation_stage.replaceAll('_', ' ')
  return episode.job_status ?? 'Created'
}

/**
 * A route-level episode workspace. It hands playback to the app-shell player
 * so progress survives navigation, while keeping citation links honest until
 * the evidence graph can resolve a stable claim target.
 */
export function EpisodeLab({ episode, onClose, onRetry, onCancel }: EpisodeLabProps) {
  const setPlayingEpisode = useAudioPlayerStore((state) => state.setEpisode)
  const setPosition = useAudioPlayerStore((state) => state.setPosition)
  const [currentTime, setCurrentTime] = useState(0)
  const [citationNotice, setCitationNotice] = useState<string | null>(null)
  const audioPath = episode.audio_url ?? episode.audio_file
  const canDownload = Boolean(episode.audio_url?.startsWith('/'))
  const canRetry = FAILED_EPISODE_STATUSES.includes(episode.job_status ?? 'unknown')
  const canCancel = ACTIVE_EPISODE_STATUSES.includes(episode.job_status ?? 'unknown')
    && episode.generation_stage !== 'awaiting_review'

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
    setCurrentTime(seconds)
    setPosition(episode.id, seconds)
  }

  return (
    <section aria-label="Episode Lab" className="space-y-4 rounded-md border bg-card p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Episode Lab</h2>
          <p className="text-sm text-muted-foreground">{episode.name}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>Close Episode Lab</Button>
      </header>

      <section aria-labelledby="episode-lab-stage-history" className="rounded border p-3">
        <h3 id="episode-lab-stage-history" className="font-medium">Stage History</h3>
        <ol className="mt-2 flex flex-wrap gap-2 text-sm">
          <li className="rounded bg-muted px-2 py-1">Created</li>
          <li className="rounded bg-muted px-2 py-1">Current: {stageLabel(episode)}</li>
          <li className="rounded border border-dashed px-2 py-1 text-muted-foreground">Evidence — Phase 3</li>
          <li className="rounded border border-dashed px-2 py-1 text-muted-foreground">Verification — Phase 3</li>
        </ol>
      </section>

      <section aria-labelledby="episode-lab-audio" className="rounded border p-3">
        <h3 id="episode-lab-audio" className="font-medium">Audio and Transcript</h3>
        <p className="mt-1 text-sm text-muted-foreground">Playback continues in the route-persistent global player.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={playInGlobalPlayer} disabled={!audioPath}>Play in global player</Button>
          {canDownload ? <Button asChild type="button" size="sm" variant="outline"><a href={episode.audio_url!} download>Download audio</a></Button> : <Button type="button" size="sm" variant="outline" disabled>Download audio</Button>}
        </div>
        <div className="mt-3">
          <SyncedTranscript
            segments={episode.transcript_segments ?? []}
            currentTime={currentTime}
            onSeek={seek}
            onCitationClick={() => setCitationNotice('Source citation — claim evidence mapping arrives in Phase 3')}
          />
          {citationNotice ? <p role="status" className="mt-2 text-sm text-muted-foreground">{citationNotice}</p> : null}
        </div>
      </section>

      {(canRetry && onRetry) || (canCancel && onCancel) ? <section aria-label="Episode actions" className="flex flex-wrap gap-2">
        {canRetry && onRetry ? <Button type="button" size="sm" variant="outline" onClick={() => onRetry(episode.id)}>Retry episode</Button> : null}
        {canCancel && onCancel ? <Button type="button" size="sm" variant="outline" onClick={() => onCancel(episode.id)}>Cancel episode</Button> : null}
      </section> : null}
    </section>
  )
}
