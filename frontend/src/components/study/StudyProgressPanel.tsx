'use client'

import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type StudyMasteryStatus = 'needs_review' | 'developing' | 'mastered'
export type StudyAdaptationAction = 'prerequisite_detour' | 'schedule_review' | 'extra_practice' | 'slow_pacing'
export type StudyProposalStatus = 'proposed' | 'accepted' | 'dismissed'

export interface StudyMasteryConcept {
  concept_id: string
  unit_id: string | null
  score: number
  status: StudyMasteryStatus
  attempts: number
  last_activity_at: string | null
  lapses: number
}

export interface StudyReviewConsistency {
  reviews: number
  lapses: number
  due_reviews: number
  on_time_rate: number
}

export interface StudyAdaptationProposal {
  schema_version: 1
  proposal_id: string
  concept_id: string | null
  unit_id: string | null
  action: StudyAdaptationAction
  title: string
  rationale: string
  status: StudyProposalStatus
  available: boolean
}

export interface StudyMasteryProjection {
  schema_version: 1
  concepts: StudyMasteryConcept[]
  review_consistency: StudyReviewConsistency
  proposals: StudyAdaptationProposal[]
  generated_at: string
  memory_writes: string[]
}

export type StudyProgressPanelState = 'loading' | 'empty' | 'error' | 'ready'

export interface StudyProgressPanelProps {
  state?: StudyProgressPanelState
  projection?: StudyMasteryProjection | null
  onRetry?: () => void
  onAccept?: (proposalId: string) => void | Promise<void>
  onDismiss?: (proposalId: string) => void | Promise<void>
}

const ACTIONS = new Set<StudyAdaptationAction>([
  'prerequisite_detour',
  'schedule_review',
  'extra_practice',
  'slow_pacing',
])
const STATUSES = new Set<StudyMasteryStatus>(['needs_review', 'developing', 'mastered'])

function isVisibleText(value: unknown, max = 2_000): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max && value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value)
}

function isFiniteRatio(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function isAwareIsoTimestamp(value: unknown): value is string {
  return isVisibleText(value, 128) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
}

/** Strict runtime decoder for API/IPC projections before they reach the panel. */
export function decodeStudyMasteryProjection(value: unknown): StudyMasteryProjection {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid Study progress response')
  const record = value as Record<string, unknown>
  const topKeys = new Set(['schema_version', 'concepts', 'review_consistency', 'proposals', 'generated_at', 'memory_writes'])
  if (Object.keys(record).some((key) => !topKeys.has(key)) || Object.keys(record).length !== topKeys.size || record.schema_version !== 1 || !Array.isArray(record.memory_writes) || record.memory_writes.length !== 0) throw new Error('Invalid Study progress response')
  if (record.memory_writes.some((item) => !isVisibleText(item, 128))) throw new Error('Invalid Study progress response')
  if (!Array.isArray(record.concepts) || record.concepts.length > 500 || !Array.isArray(record.proposals) || record.proposals.length > 100) throw new Error('Invalid Study progress response')
  if (!isAwareIsoTimestamp(record.generated_at)) throw new Error('Invalid Study progress response')
  const consistency = record.review_consistency
  if (!consistency || typeof consistency !== 'object' || Array.isArray(consistency)) throw new Error('Invalid Study progress response')
  const review = consistency as Record<string, unknown>
  if (Object.keys(review).some((key) => !['reviews', 'lapses', 'due_reviews', 'on_time_rate'].includes(key)) || Object.keys(review).length !== 4) throw new Error('Invalid Study progress response')
  if (![review.reviews, review.lapses, review.due_reviews].every((item) => Number.isInteger(item) && (item as number) >= 0 && (item as number) <= 500) || !isFiniteRatio(review.on_time_rate)) throw new Error('Invalid Study progress response')
  const concepts = record.concepts.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('Invalid Study progress response')
    const concept = item as Record<string, unknown>
    if (Object.keys(concept).some((key) => !['concept_id', 'unit_id', 'score', 'status', 'attempts', 'last_activity_at', 'lapses'].includes(key))) throw new Error('Invalid Study progress response')
    if (!isVisibleText(concept.concept_id, 128) || (concept.unit_id !== null && !isVisibleText(concept.unit_id, 64)) || !isFiniteRatio(concept.score) || typeof concept.status !== 'string' || !STATUSES.has(concept.status as StudyMasteryStatus) || !Number.isInteger(concept.attempts) || (concept.attempts as number) < 0 || (concept.attempts as number) > 500 || !Number.isInteger(concept.lapses) || (concept.lapses as number) < 0 || (concept.lapses as number) > 500 || (concept.last_activity_at !== null && !isAwareIsoTimestamp(concept.last_activity_at))) throw new Error('Invalid Study progress response')
    return {
      concept_id: concept.concept_id,
      unit_id: concept.unit_id as string | null,
      score: concept.score,
      status: concept.status as StudyMasteryStatus,
      attempts: concept.attempts as number,
      last_activity_at: concept.last_activity_at as string | null,
      lapses: concept.lapses as number,
    }
  })
  const proposals = record.proposals.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('Invalid Study progress response')
    const proposal = item as Record<string, unknown>
    if (Object.keys(proposal).some((key) => !['schema_version', 'proposal_id', 'concept_id', 'unit_id', 'action', 'title', 'rationale', 'status', 'available'].includes(key)) || Object.keys(proposal).length !== 9) throw new Error('Invalid Study progress response')
    if (proposal.schema_version !== 1 || !isVisibleText(proposal.proposal_id, 512) || (proposal.concept_id !== null && !isVisibleText(proposal.concept_id, 128)) || (proposal.unit_id !== null && !isVisibleText(proposal.unit_id, 64)) || typeof proposal.action !== 'string' || !ACTIONS.has(proposal.action as StudyAdaptationAction) || !isVisibleText(proposal.title, 200) || !isVisibleText(proposal.rationale, 2_000) || !['proposed', 'accepted', 'dismissed'].includes(String(proposal.status)) || typeof proposal.available !== 'boolean') throw new Error('Invalid Study progress response')
    return {
      schema_version: 1 as const,
      proposal_id: proposal.proposal_id,
      concept_id: proposal.concept_id as string | null,
      unit_id: proposal.unit_id as string | null,
      action: proposal.action as StudyAdaptationAction,
      title: proposal.title,
      rationale: proposal.rationale,
      status: proposal.status as StudyProposalStatus,
      available: proposal.available,
    }
  })
  return {
    schema_version: 1,
    concepts,
    review_consistency: {
      reviews: review.reviews as number,
      lapses: review.lapses as number,
      due_reviews: review.due_reviews as number,
      on_time_rate: review.on_time_rate as number,
    },
    proposals,
    generated_at: record.generated_at,
    memory_writes: [],
  }
}

export function StudyProgressPanel({ state, projection, onRetry, onAccept, onDismiss }: StudyProgressPanelProps) {
  const [pending, setPending] = useState<{ proposal: StudyAdaptationProposal; decision: 'accepted' | 'dismissed' } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [decisionError, setDecisionError] = useState(false)
  const effectiveState = state ?? (projection && projection.concepts.length > 0 ? 'ready' : 'empty')
  const decoded = useMemo(() => {
    if (effectiveState !== 'ready' || !projection) return null
    try {
      return decodeStudyMasteryProjection(projection)
    } catch {
      return null
    }
  }, [effectiveState, projection])

  if (effectiveState === 'loading') {
    return <Card aria-label="Study progress"><CardContent className="p-6"><p role="status">Loading study progress…</p></CardContent></Card>
  }
  if (effectiveState === 'error') {
    return <Card aria-label="Study progress"><CardContent className="space-y-3 p-6"><p role="alert" className="text-sm text-destructive">Study progress could not be loaded.</p><Button type="button" variant="outline" onClick={onRetry}>Retry</Button></CardContent></Card>
  }
  if (effectiveState === 'empty' || !decoded) {
    return <Card aria-label="Study progress"><CardHeader><CardTitle className="text-base">Study progress</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">No study progress yet.</p></CardContent></Card>
  }

  const confirm = async () => {
    if (!pending) return
    setSubmitting(true)
    setDecisionError(false)
    try {
      if (pending.decision === 'accepted') await onAccept?.(pending.proposal.proposal_id)
      else await onDismiss?.(pending.proposal.proposal_id)
      setPending(null)
    } catch {
      setDecisionError(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card aria-label="Study progress">
      <CardHeader className="border-b pb-4">
        <CardTitle className="text-lg">Study progress</CardTitle>
        <CardDescription>{decoded.concepts.length} concepts · {decoded.review_consistency.reviews} native reviews · {Math.round(decoded.review_consistency.on_time_rate * 100)}% on time</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        <ul role="list" aria-label="Concept mastery" className="space-y-3">
          {decoded.concepts.map((concept) => (
            <li key={concept.concept_id} className="rounded-md border p-3">
              <div className="flex items-center justify-between gap-3"><span className="font-medium">{concept.concept_id}</span><span className="text-xs text-muted-foreground">{concept.status.replaceAll('_', ' ')}</span></div>
              <div className="mt-2 h-2 rounded-full bg-muted" aria-label={`${concept.concept_id} mastery`}><div className="h-2 rounded-full bg-primary" style={{ width: `${Math.round(concept.score * 100)}%` }} /></div>
              <p className="mt-1 text-xs text-muted-foreground">{Math.round(concept.score * 100)}% · {concept.attempts} observation{concept.attempts === 1 ? '' : 's'}</p>
            </li>
          ))}
        </ul>

        <section aria-labelledby="study-adaptations-heading" className="space-y-3">
          <h3 id="study-adaptations-heading" className="text-sm font-semibold">Suggested adaptations</h3>
          {decoded.proposals.length === 0 ? <p className="text-sm text-muted-foreground">No adaptations are suggested right now.</p> : (
            <ul role="list" className="space-y-3">
              {decoded.proposals.map((proposal) => (
                <li key={proposal.proposal_id} className="rounded-md border p-3">
                  <p className="font-medium">{proposal.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{proposal.rationale}</p>
                  {proposal.available && proposal.status === 'proposed' && (onAccept || onDismiss) ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {onAccept ? <Button type="button" size="sm" onClick={() => setPending({ proposal, decision: 'accepted' })} aria-label={`Accept ${proposal.title}`}>Accept {proposal.title}</Button> : null}
                      {onDismiss ? <Button type="button" size="sm" variant="outline" onClick={() => setPending({ proposal, decision: 'dismissed' })}>Dismiss</Button> : null}
                    </div>
                  ) : <p className="mt-3 text-xs text-muted-foreground">This adaptation is unavailable.</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
      <Dialog open={pending !== null} onOpenChange={(open) => { if (!open && !submitting) setPending(null) }}>
        <DialogContent showCloseButton={!submitting}>
          <DialogHeader>
            <DialogTitle>Confirm {pending?.decision === 'accepted' ? 'acceptance' : 'dismissal'}</DialogTitle>
            <DialogDescription>{pending?.proposal.title} will be recorded as an explicit user decision.</DialogDescription>
          </DialogHeader>
          {decisionError ? <p role="alert" className="text-sm text-destructive">The decision could not be saved. Try again.</p> : null}
          <DialogFooter><Button type="button" onClick={() => void confirm()} disabled={submitting}>{submitting ? 'Saving…' : 'Confirm'}</Button><Button type="button" variant="outline" onClick={() => setPending(null)} disabled={submitting}>Cancel</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
