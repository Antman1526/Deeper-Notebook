'use client'

import { useId } from 'react'
import { Podcast } from 'lucide-react'

import type { PodcastDestination, PodcastSelection } from '@/lib/podcasts/selection'
import { Button } from '@/components/ui/button'

interface TurnIntoPodcastActionProps {
  selection: PodcastSelection
  destination: PodcastDestination
  disabledReason?: string
  onOpen: (selections: PodcastSelection[], destination: PodcastDestination) => void
}

/**
 * A side-effect-free entry point: it only opens a review surface. Generation
 * remains an explicit confirmation step owned by Quick Podcast or Studio.
 */
export function TurnIntoPodcastAction({
  selection,
  destination,
  disabledReason,
  onOpen,
}: TurnIntoPodcastActionProps) {
  const actionId = useId()
  const reasonId = disabledReason ? `podcast-unavailable-${actionId}` : undefined

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={Boolean(disabledReason)}
        aria-describedby={reasonId}
        onClick={(event) => {
          event.stopPropagation()
          onOpen([selection], destination)
        }}
      >
        <Podcast aria-hidden="true" />
        Turn into podcast
      </Button>
      {disabledReason ? (
        <p id={reasonId} className="text-xs text-muted-foreground" role="status">
          {disabledReason}
        </p>
      ) : null}
    </div>
  )
}
