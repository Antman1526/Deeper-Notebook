'use client'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { TranscriptSegment } from '@/lib/types/podcasts'

interface SyncedTranscriptProps {
  segments: TranscriptSegment[]
  currentTime: number
  onSeek: (seconds: number) => void
  onCitationClick?: (citationId: string) => void
}

function formatTimestamp(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

export function SyncedTranscript({
  segments,
  currentTime,
  onSeek,
  onCitationClick,
}: SyncedTranscriptProps) {
  if (segments.length === 0) {
    return <p className="text-sm text-muted-foreground">Transcript timing is not available for this overview.</p>
  }

  return (
    <div aria-label="Synced transcript" className="max-h-56 space-y-2 overflow-y-auto pr-1">
      {segments.map((segment, index) => {
        const active = currentTime >= segment.start_seconds && currentTime < segment.end_seconds
        return (
          <article
            key={`${segment.start_seconds}-${index}`}
            className={cn(
              'rounded-md border p-3 text-sm transition-colors',
              active ? 'border-primary bg-primary/5' : 'bg-background',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-auto px-0 py-0 font-medium"
                onClick={() => onSeek(segment.start_seconds)}
              >
                {formatTimestamp(segment.start_seconds)} {segment.speaker}
              </Button>
              {segment.citation_ids.map((citationId) => (
                <Button
                  key={citationId}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onCitationClick?.(citationId)}
                >
                  {citationId}
                </Button>
              ))}
            </div>
            <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{segment.text}</p>
          </article>
        )
      })}
    </div>
  )
}
