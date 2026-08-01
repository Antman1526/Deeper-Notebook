'use client'

import { useId } from 'react'
import { Podcast } from 'lucide-react'

import type { PodcastDestination, PodcastSelection } from '@/lib/podcasts/selection'
import { Button } from '@/components/ui/button'

interface TurnIntoPodcastActionProps {
  selection?: PodcastSelection
  selections?: PodcastSelection[]
  destination: PodcastDestination
  label?: string
  disabledReason?: string
  onOpen: (selections: PodcastSelection[], destination: PodcastDestination) => void
}

/**
 * A side-effect-free entry point: it only opens a review surface. Generation
 * remains an explicit confirmation step owned by Quick Podcast or Studio.
 */
export function TurnIntoPodcastAction({
  selection,
  selections,
  destination,
  label = 'Turn into podcast',
  disabledReason,
  onOpen,
}: TurnIntoPodcastActionProps) {
  const actionId = useId()
  const resolvedSelections = selections ?? (selection ? [selection] : [])
  const unavailableReason = disabledReason ?? (
    resolvedSelections.length === 0 ? 'No readable content is available' : undefined
  )
  const reasonId = unavailableReason ? `podcast-unavailable-${actionId}` : undefined

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={Boolean(unavailableReason)}
        aria-describedby={reasonId}
        onClick={(event) => {
          event.stopPropagation()
          onOpen(resolvedSelections, destination)
        }}
      >
        <Podcast aria-hidden="true" />
        {label}
      </Button>
      {unavailableReason ? (
        <p id={reasonId} className="text-xs text-muted-foreground">
          {unavailableReason}
        </p>
      ) : null}
    </div>
  )
}
