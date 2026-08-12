'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

export type OutlineStoryboardSegment = string | { id?: string; title?: string; name?: string; description?: string }

export interface OutlineStoryboardProps {
  segments: OutlineStoryboardSegment[]
  onChange: (segments: OutlineStoryboardSegment[]) => void
}

function segmentTitle(segment: OutlineStoryboardSegment): string {
  if (typeof segment === 'string') return segment
  return segment.title ?? segment.name ?? segment.id ?? 'Untitled segment'
}

interface SegmentIdentityState {
  labels: string[]
  ids: string[]
}

function reconcileIdentities(previous: SegmentIdentityState, labels: string[], segments: OutlineStoryboardSegment[]): SegmentIdentityState {
  const used = new Set<number>()
  const ids = labels.map((label, index) => {
    const previousIndex = previous.labels.findIndex((previousLabel, candidateIndex) => !used.has(candidateIndex) && previousLabel === label)
    if (previousIndex >= 0) {
      used.add(previousIndex)
      return previous.ids[previousIndex]
    }
    const sourceId = typeof segments[index] === 'object' && segments[index]?.id ? segments[index].id : `segment-${index + 1}`
    const duplicateCount = labels.slice(0, index + 1).filter((candidate) => candidate === label).length
    return `${sourceId}-${duplicateCount}`
  })
  return { labels: [...labels], ids }
}

export function OutlineStoryboard({ segments, onChange }: OutlineStoryboardProps) {
  const labels = useMemo(() => segments.map(segmentTitle), [segments])
  const [announcement, setAnnouncement] = useState('')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [identityState, setIdentityState] = useState<SegmentIdentityState>(() => reconcileIdentities({ labels: [], ids: [] }, labels, segments))
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const itemRefs = useRef<Record<string, HTMLLIElement | null>>({})
  const identitiesMatch = identityState.labels.length === labels.length && identityState.labels.every((label, index) => label === labels[index])
  const segmentIds = identitiesMatch ? identityState.ids : reconcileIdentities(identityState, labels, segments).ids

  useEffect(() => {
    if (!identitiesMatch) setIdentityState(reconcileIdentities(identityState, labels, segments))
  }, [identitiesMatch, identityState, labels, segments])

  const reorder = (from: number, to: number, focusMovedItem = true) => {
    if (from === to || from < 0 || to < 0 || from >= labels.length || to >= labels.length) return
    const moved = labels[from]
    const movedSegment = segments[from]
    const movedId = segmentIds[from]
    const next = [...segments]
    next.splice(from, 1)
    next.splice(to, 0, movedSegment)
    const nextLabels = [...labels]
    nextLabels.splice(from, 1)
    nextLabels.splice(to, 0, moved)
    const nextIds = [...segmentIds]
    nextIds.splice(from, 1)
    nextIds.splice(to, 0, movedId)
    setIdentityState({ labels: nextLabels, ids: nextIds })
    onChange(next)
    setAnnouncement(`${moved} moved to position ${to + 1}`)
    if (focusMovedItem) itemRefs.current[movedId]?.focus()
  }

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= labels.length) return
    const movedId = segmentIds[index]
    const focusTarget = buttonRefs.current[`${movedId}:${direction}`]
    focusTarget?.focus()
    reorder(index, target, false)
    focusTarget?.focus()
  }

  return (
    <section data-region="outline-storyboard" aria-label="Outline Storyboard" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Outline Storyboard</h3>
        <p className="mt-1 text-sm text-muted-foreground">Outline storyboard review is the current Phase-2 gate; cited storyboard artifacts arrive in Phase 3.</p>
      </header>
      <ol className="space-y-2" aria-label="Outline segments">
        {labels.map((label, index) => {
          const segmentId = segmentIds[index]
          return (
          <li
            key={segmentId}
            ref={(element) => { itemRefs.current[segmentId] = element }}
            tabIndex={-1}
            draggable
            aria-label={label}
            data-segment-id={segmentId}
            className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm"
            onDragStart={() => setDragIndex(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => { if (dragIndex != null) reorder(dragIndex, index); setDragIndex(null) }}
          >
            <span>{label}</span>
            <span className="flex flex-wrap gap-2">
              <Button ref={(element) => { buttonRefs.current[`${segmentId}:-1`] = element }} type="button" size="sm" variant="outline" disabled={index === 0} aria-label={`Move ${label} earlier`} onClick={() => move(index, -1)}>Move earlier</Button>
              <Button ref={(element) => { buttonRefs.current[`${segmentId}:1`] = element }} type="button" size="sm" variant="outline" disabled={index === labels.length - 1} aria-label={`Move ${label} later`} onClick={() => move(index, 1)}>Move later</Button>
            </span>
          </li>
          )
        })}
      </ol>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </section>
  )
}
