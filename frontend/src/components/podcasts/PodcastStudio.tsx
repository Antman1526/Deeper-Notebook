'use client'

import { useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { podcastsApi } from '@/lib/api/podcasts'
import type { PodcastReadiness } from '@/lib/types/podcasts'
import type { PodcastSelection } from '@/lib/podcasts/selection'

interface PodcastStudioProps {
  seedDocumentIds: string[]
  selections?: PodcastSelection[]
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
export function PodcastStudio({ seedDocumentIds, selections, modelPlans = [] }: PodcastStudioProps) {
  const [centralQuestion, setCentralQuestion] = useState('')
  const [audience, setAudience] = useState('practitioner')
  const [outline, setOutline] = useState(['Introduction', 'Findings', 'Takeaway'])
  const [announcement, setAnnouncement] = useState('')
  const [readiness, setReadiness] = useState<PodcastReadiness | null>(null)
  const [episodeProfiles, setEpisodeProfiles] = useState<string[]>([])
  const [speakerProfiles, setSpeakerProfiles] = useState<string[]>([])
  const [episodeProfile, setEpisodeProfile] = useState('')
  const [speakerProfile, setSpeakerProfile] = useState('')
  const [productionPhase, setProductionPhase] = useState<'review' | 'confirm'>('review')
  const [isPreparing, setIsPreparing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [productionError, setProductionError] = useState<string | null>(null)
  const [submittedMessage, setSubmittedMessage] = useState<string | null>(null)
  const moveRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const submissionKey = useRef<string | null>(null)
  const resolvedSelections = selections ?? seedDocumentIds.map((documentId) => ({
    kind: 'knowledge_document' as const,
    documentId,
  }))
  const prepareProductionReview = async () => {
    if (isPreparing || resolvedSelections.length === 0) return
    setIsPreparing(true)
    setProductionError(null)
    setSubmittedMessage(null)
    try {
      const [nextReadiness, nextEpisodeProfiles, nextSpeakerProfiles] = await Promise.all([
        podcastsApi.getPodcastReadiness(resolvedSelections),
        podcastsApi.listEpisodeProfiles(),
        podcastsApi.listSpeakerProfiles(),
      ])
      setReadiness(nextReadiness)
      const nextEpisodeNames = nextEpisodeProfiles.map((profile) => profile.name)
      const nextSpeakerNames = nextSpeakerProfiles.map((profile) => profile.name)
      setEpisodeProfiles(nextEpisodeNames)
      setSpeakerProfiles(nextSpeakerNames)
      setEpisodeProfile((current) => current || nextEpisodeNames[0] || '')
      setSpeakerProfile((current) => current || nextSpeakerNames[0] || '')
      setProductionPhase('review')
    } catch {
      setProductionError('Podcast readiness is unavailable. No production was started.')
    } finally {
      setIsPreparing(false)
    }
  }
  const canConfirm = Boolean(
    readiness?.ready
      && readiness.preview.selectionFingerprint
      && episodeProfile
      && speakerProfile,
  )
  const confirmProduction = async () => {
    if (!readiness || !canConfirm || isSubmitting) return
    setIsSubmitting(true)
    setProductionError(null)
    submissionKey.current ??= `podcast-studio-${crypto.randomUUID()}`
    try {
      const submitted = await podcastsApi.submitStudioPodcast({
        selections: resolvedSelections,
        selectionFingerprint: readiness.preview.selectionFingerprint,
        idempotencyKey: submissionKey.current,
        episodeProfile,
        speakerProfile,
        episodeName: readiness.preview.entries[0]?.title ?? 'Deeper Notebook podcast',
        reviewOutline: true,
        editorialBrief: {
          centralQuestion: centralQuestion || null,
          audience,
          outline,
        },
      })
      setSubmittedMessage(`Production submitted: ${submitted.episodeName}. Outline review is next.`)
    } catch {
      setProductionError('Production could not be submitted. Review readiness and try again.')
    } finally {
      setIsSubmitting(false)
    }
  }
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
          <p className="mt-1 text-sm text-muted-foreground">{`${resolvedSelections.length} selected reference${resolvedSelections.length === 1 ? '' : 's'}`} · references only, never source paths.</p>
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
      <section className="rounded-md border p-4" aria-labelledby="podcast-studio-production-review">
        <h3 id="podcast-studio-production-review" className="font-semibold">Production Review</h3>
        <p className="mt-1 text-sm text-muted-foreground">Readiness is checked only when you request review. Production still requires a separate confirmation.</p>
        {!readiness ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button type="button" onClick={() => void prepareProductionReview()} disabled={isPreparing || resolvedSelections.length === 0}>
              {isPreparing ? 'Checking readiness…' : 'Prepare production review'}
            </Button>
            {resolvedSelections.length === 0 ? <p className="text-sm text-muted-foreground">Choose at least one readable source before production review.</p> : null}
          </div>
        ) : (
          <div className="mt-3 space-y-3">
            <p className="text-sm text-muted-foreground">{readiness.ready ? 'Local readiness is verified for this selection.' : readiness.blockedReasons.join(', ') || 'Local readiness is blocked.'}</p>
            <section aria-labelledby="podcast-studio-profiles" className="grid gap-3 sm:grid-cols-2">
              <h4 id="podcast-studio-profiles" className="sr-only">Production profiles</h4>
              <label className="grid gap-1 text-sm">Episode profile<select aria-label="Episode profile" value={episodeProfile} onChange={(event) => setEpisodeProfile(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="">Choose a profile</option>{episodeProfiles.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
              <label className="grid gap-1 text-sm">Voice profile<select aria-label="Voice profile" value={speakerProfile} onChange={(event) => setSpeakerProfile(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="">Choose a profile</option>{speakerProfiles.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
            </section>
            {productionPhase === 'review' ? (
              <Button type="button" onClick={() => setProductionPhase('confirm')} disabled={!canConfirm}>Continue to confirmation</Button>
            ) : (
              <div className="space-y-2 rounded border bg-muted/20 p-3">
                <p className="text-sm">Confirm one fingerprint-checked local production job. It will stop for outline review before script and voice generation.</p>
                <Button type="button" onClick={() => void confirmProduction()} disabled={!canConfirm || isSubmitting}>{isSubmitting ? 'Submitting…' : 'Confirm production'}</Button>
              </div>
            )}
          </div>
        )}
        {productionError ? <p role="alert" className="mt-3 text-sm text-destructive">{productionError}</p> : null}
        {submittedMessage ? <p role="status" className="mt-3 text-sm text-muted-foreground">{submittedMessage}</p> : null}
      </section>
      <p className="text-sm text-muted-foreground">Opening the Studio does not submit a production job.</p>
    </section>
  )
}
