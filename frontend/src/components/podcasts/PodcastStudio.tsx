'use client'

import { useRef, useState } from 'react'

import { Button } from '@/components/ui/button'

interface PodcastStudioProps {
  seedDocumentIds: string[]
  modelPlans?: Array<{
    label: string
    plan: { outcome: 'ready' | 'blocked' | 'approval_required'; reason: string } | undefined
  }>
}

const timeline = [
  ['Research Set Preview', 'Current selection'],
  ['Editorial Brief', 'Configure before production'],
  ['Outline Storyboard', 'Current review gate'],
  ['Script/Voice Job', 'Begins after outline approval'],
  ['Episode', 'Current production output'],
] as const

/**
 * Shared Phase-2 controller shell. It presents only current, reviewable
 * production stages and makes the later evidence engine boundary explicit.
 */
export function PodcastStudio({ seedDocumentIds, modelPlans = [] }: PodcastStudioProps) {
  const [centralQuestion, setCentralQuestion] = useState('')
  const [audience, setAudience] = useState('practitioner')
  const [outline, setOutline] = useState(['Introduction', 'Findings', 'Takeaway'])
  const [announcement, setAnnouncement] = useState('')
  const moveRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const moveOutline = (index: number, direction: -1 | 1) => {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= outline.length) return
    const moved = outline[index]
    const next = [...outline]
    next.splice(index, 1)
    next.splice(targetIndex, 0, moved)
    moveRefs.current[`${moved}:${direction}`]?.focus()
    setOutline(next)
    setAnnouncement(`${moved} moved to position ${targetIndex + 1}`)
  }
  return (
    <section aria-label="Podcast Intelligence Studio" className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Podcast Intelligence Studio</h2>
        <p className="mt-1 text-sm text-muted-foreground">Build an optional, source-grounded audio overview. Production remains a separate confirmation.</p>
      </header>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="rounded-md border p-4" aria-labelledby="podcast-studio-research-set">
          <h3 id="podcast-studio-research-set" className="font-semibold">Research Set</h3>
          <p className="mt-1 text-sm text-muted-foreground">{`${seedDocumentIds.length} selected document${seedDocumentIds.length === 1 ? '' : 's'}`} · references only, never source paths.</p>
        </section>
        <section className="rounded-md border p-4" aria-labelledby="podcast-studio-brief">
          <h3 id="podcast-studio-brief" className="font-semibold">Editorial Brief</h3>
          <p className="mt-1 text-sm text-muted-foreground">Briefing and model choices are reviewed before any production job is submitted.</p>
          <label className="mt-3 grid gap-1 text-sm" htmlFor="podcast-central-question">Central question<textarea id="podcast-central-question" value={centralQuestion} onChange={event => setCentralQuestion(event.target.value)} className="min-h-20 rounded-md border bg-background p-2" /></label>
          <label className="mt-3 grid gap-1 text-sm" htmlFor="podcast-audience">Audience<select id="podcast-audience" value={audience} onChange={event => setAudience(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="foundation">Foundation</option><option value="practitioner">Practitioner</option><option value="expert">Expert</option></select></label>
        </section>
      </div>
      <section className="rounded-md border p-4" aria-labelledby="podcast-studio-storyboard">
        <h3 id="podcast-studio-storyboard" className="font-semibold">Outline Storyboard</h3>
        <p className="mt-1 text-sm text-muted-foreground">Outline storyboard review is the current production gate.</p>
        <ol className="mt-3 space-y-2">{outline.map((segment, index) => <li key={segment} className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm"><span>{segment}</span><span className="flex gap-2"><Button ref={element => { moveRefs.current[`${segment}:-1`] = element }} type="button" size="sm" variant="outline" disabled={index === 0} aria-label={`Move ${segment} earlier`} onClick={() => moveOutline(index, -1)}>Move earlier</Button><Button ref={element => { moveRefs.current[`${segment}:1`] = element }} type="button" size="sm" variant="outline" disabled={index === outline.length - 1} aria-label={`Move ${segment} later`} onClick={() => moveOutline(index, 1)}>Move later</Button></span></li>)}</ol>
        <p className="sr-only" role="status">{announcement}</p>
      </section>
      <section className="rounded-md border p-4" aria-labelledby="podcast-studio-timeline">
        <h3 id="podcast-studio-timeline" className="font-semibold">Production Timeline</h3>
        <ol className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {timeline.map(([stage, detail]) => <li key={stage} className="rounded border bg-muted/30 p-2 text-sm"><span className="font-medium">{stage}</span><span className="mt-1 block text-xs text-muted-foreground">{detail}</span></li>)}
        </ol>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {['Evidence', 'Verification'].map(stage => <div key={stage} className="rounded border border-dashed p-3 text-sm"><span className="font-medium">{stage}</span><span className="mt-1 block text-xs text-muted-foreground">Available after intellectual engine upgrade</span></div>)}
        </div>
      </section>
      {modelPlans.length > 0 && <section className="rounded-md border p-4" aria-label="Model plan"><h3 className="font-semibold">Model Plan</h3><ul className="mt-2 grid gap-2 sm:grid-cols-2">{modelPlans.map(({ label, plan }) => <li key={label} className="text-sm"><span className="font-medium">{label}</span><span className="text-muted-foreground"> · {plan?.outcome ?? 'blocked'} · {plan?.reason ?? 'Route plan unavailable.'}</span></li>)}</ul></section>}
      <p className="text-sm text-muted-foreground">No production job is submitted from this planning surface.</p>
    </section>
  )
}
