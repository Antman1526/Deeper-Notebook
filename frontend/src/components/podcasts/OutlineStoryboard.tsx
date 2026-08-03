'use client'

import { useRef, useState } from 'react'

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

export function OutlineStoryboard({ segments, onChange }: OutlineStoryboardProps) {
  const labels = segments.map(segmentTitle)
  const [announcement, setAnnouncement] = useState('')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const itemRefs = useRef<Record<string, HTMLLIElement | null>>({})

  const reorder = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= labels.length || to >= labels.length) return
    const moved = labels[from]
    const movedSegment = segments[from]
    const next = [...segments]
    next.splice(from, 1)
    next.splice(to, 0, movedSegment)
    onChange(next)
    setAnnouncement(`${moved} moved to position ${to + 1}`)
    itemRefs.current[moved]?.focus()
  }

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= labels.length) return
    const moved = labels[index]
    reorder(index, target)
    buttonRefs.current[`${moved}:${direction}`]?.focus()
  }

  return (
    <section data-region="outline-storyboard" aria-label="Outline Storyboard" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Outline Storyboard</h3>
        <p className="mt-1 text-sm text-muted-foreground">Outline storyboard review is the current Phase-2 gate; cited storyboard artifacts arrive in Phase 3.</p>
      </header>
      <ol className="space-y-2" aria-label="Outline segments">
        {labels.map((label, index) => (
          <li
            key={label}
            ref={(element) => { itemRefs.current[label] = element }}
            tabIndex={-1}
            draggable
            aria-label={label}
            className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm"
            onDragStart={() => setDragIndex(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => { if (dragIndex != null) reorder(dragIndex, index); setDragIndex(null) }}
          >
            <span>{label}</span>
            <span className="flex gap-2">
              <Button ref={(element) => { buttonRefs.current[`${label}:-1`] = element }} type="button" size="sm" variant="outline" disabled={index === 0} aria-label={`Move ${label} earlier`} onClick={() => move(index, -1)}>Move earlier</Button>
              <Button ref={(element) => { buttonRefs.current[`${label}:1`] = element }} type="button" size="sm" variant="outline" disabled={index === labels.length - 1} aria-label={`Move ${label} later`} onClick={() => move(index, 1)}>Move later</Button>
            </span>
          </li>
        ))}
      </ol>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </section>
  )
}
