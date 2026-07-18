'use client'

import { useEffect, useRef, useState } from 'react'
import { Pause, Play, Square, Volume2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { resolvePodcastAssetUrl } from '@/lib/api/podcasts'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'
import { SyncedTranscript } from './SyncedTranscript'

async function fetchPlayableUrl(path: string, signal: AbortSignal): Promise<string> {
  const url = await resolvePodcastAssetUrl(path)
  if (!url) throw new Error('Audio path is unavailable')

  const raw = window.localStorage.getItem('auth-storage')
  let token: string | undefined
  if (raw) {
    try {
      token = JSON.parse(raw)?.state?.token
    } catch {
      // A malformed legacy auth cache must not make local media unusable.
    }
  }
  if (!token) return url

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!response.ok) throw new Error(`Audio request failed (${response.status})`)
  return URL.createObjectURL(await response.blob())
}

function formatTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

export function GlobalAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement>(null)
  const objectUrlRef = useRef<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [volume, setVolume] = useState(0.9)
  const [rate, setRate] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const { episode, requestedPlayback, setPosition, requestPlayback, pause, clear } = useAudioPlayerStore()
  const episodeId = episode?.id
  const sourcePath = episode?.sourcePath

  useEffect(() => {
    if (!episodeId || !sourcePath || !audioRef.current) return
    const controller = new AbortController()
    let cancelled = false
    setError(null)

    void fetchPlayableUrl(sourcePath, controller.signal)
      .then((url) => {
        if (cancelled || !audioRef.current) {
          if (url.startsWith('blob:')) URL.revokeObjectURL(url)
          return
        }
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = url.startsWith('blob:') ? url : null
        audioRef.current.src = url
        const currentPlayerState = useAudioPlayerStore.getState()
        audioRef.current.currentTime = currentPlayerState.positionByEpisode[episodeId] ?? 0
        if (currentPlayerState.requestedPlayback) void Promise.resolve(audioRef.current.play()).catch(() => pause())
      })
      .catch((loadError: unknown) => {
        if (!cancelled && (loadError as Error).name !== 'AbortError') {
          setError('Audio could not be loaded locally.')
          pause()
        }
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [episodeId, sourcePath, pause])

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
  }, [])

  if (!episode) return null

  const seek = (seconds: number) => {
    if (!audioRef.current) return
    audioRef.current.currentTime = seconds
    setCurrentTime(seconds)
    setPosition(episode.id, seconds)
  }

  const togglePlayback = () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      requestPlayback()
      void Promise.resolve(audio.play()).catch(() => pause())
    } else {
      audio.pause()
      pause()
    }
  }

  return (
    <aside aria-label="Audio overview player" className="border-t bg-card px-4 py-3 shadow-[0_-4px_14px_rgb(0_0_0_/_0.06)]">
      <audio
        ref={audioRef}
        onLoadedMetadata={(event) => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)}
        onTimeUpdate={(event) => {
          const seconds = event.currentTarget.currentTime
          setCurrentTime(seconds)
          setPosition(episode.id, seconds)
        }}
        onEnded={pause}
        onPlay={requestPlayback}
        onPause={pause}
      />
      <div className="mx-auto grid max-w-6xl gap-3 lg:grid-cols-[minmax(14rem,1fr)_auto] lg:items-center">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{episode.title}</p>
          <div className="mt-2 flex items-center gap-3">
            <Button type="button" size="icon" variant="outline" aria-label={requestedPlayback ? 'Pause overview' : 'Play overview'} onClick={togglePlayback}>
              {requestedPlayback ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
            <span className="w-24 text-xs tabular-nums text-muted-foreground">{formatTime(currentTime)} / {formatTime(duration)}</span>
            <input aria-label="Playback position" type="range" value={currentTime} max={Math.max(duration, 1)} step={0.1} onChange={(event) => seek(Number(event.target.value))} className="min-w-24 flex-1 accent-primary" />
            <Volume2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input aria-label="Volume" type="range" value={volume} min={0} max={1} step={0.05} onChange={(event) => { const next = Number(event.target.value); setVolume(next); if (audioRef.current) audioRef.current.volume = next }} className="w-20 accent-primary" />
            <select aria-label="Playback speed" value={rate} onChange={(event) => { const next = Number(event.target.value); setRate(next); if (audioRef.current) audioRef.current.playbackRate = next }} className="h-8 rounded-md border bg-background px-2 text-xs">
              {[0.75, 1, 1.25, 1.5, 2].map((value) => <option key={value} value={value}>{value}x</option>)}
            </select>
            <Button type="button" size="icon" variant="ghost" aria-label="Stop overview" onClick={() => { audioRef.current?.pause(); clear() }}><Square className="h-4 w-4" /></Button>
          </div>
          {error ? <p role="alert" className="mt-2 text-xs text-destructive">{error}</p> : null}
        </div>
        <SyncedTranscript segments={episode.transcriptSegments} currentTime={currentTime} onSeek={seek} />
      </div>
    </aside>
  )
}
