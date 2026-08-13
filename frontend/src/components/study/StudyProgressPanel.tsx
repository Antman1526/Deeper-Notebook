'use client'

import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  decodeStudyMasteryProjection,
  StudyAdaptationProposal,
  StudyMasteryProjection,
} from '@/lib/types/study-progress'

export type StudyProgressPanelState = 'loading' | 'empty' | 'error' | 'ready'

export interface StudyProgressPanelProps {
  state?: StudyProgressPanelState
  projection?: StudyMasteryProjection | null
  onRetry?: () => void
  onAccept?: (proposalId: string, requestId: string) => void | Promise<void>
  onDismiss?: (proposalId: string, requestId: string) => void | Promise<void>
}

function newDecisionRequestId(): string {
  const uuid = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `study-decision:${uuid}`.slice(0, 256)
}

export function StudyProgressPanel({ state, projection, onRetry, onAccept, onDismiss }: StudyProgressPanelProps) {
  const [pending, setPending] = useState<{ proposal: StudyAdaptationProposal; decision: 'accepted' | 'dismissed'; requestId: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [decisionError, setDecisionError] = useState(false)
  const effectiveState = state ?? (projection ? 'ready' : 'empty')
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
  if (effectiveState === 'ready' && !decoded) {
    return <Card aria-label="Study progress"><CardContent className="space-y-3 p-6"><p role="alert" className="text-sm text-destructive">Study progress could not be read.</p><Button type="button" variant="outline" onClick={onRetry}>Retry</Button></CardContent></Card>
  }
  if (effectiveState === 'empty' || !decoded) {
    return <Card aria-label="Study progress"><CardHeader><CardTitle className="text-base">Study progress</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">No study progress yet.</p></CardContent></Card>
  }

  const confirm = async () => {
    if (!pending) return
    setSubmitting(true)
    setDecisionError(false)
    try {
      if (pending.decision === 'accepted') await onAccept?.(pending.proposal.proposal_id, pending.requestId)
      else await onDismiss?.(pending.proposal.proposal_id, pending.requestId)
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
                      {onAccept ? <Button type="button" size="sm" className="h-auto min-h-8 max-w-full min-w-0 whitespace-normal text-left" onClick={() => setPending({ proposal, decision: 'accepted', requestId: newDecisionRequestId() })} aria-label={`Accept ${proposal.title}`}>Accept {proposal.title}</Button> : null}
                      {onDismiss ? <Button type="button" size="sm" variant="outline" className="h-auto min-h-8 max-w-full min-w-0 whitespace-normal text-left" onClick={() => setPending({ proposal, decision: 'dismissed', requestId: newDecisionRequestId() })} aria-label={`Dismiss ${proposal.title}`}>Dismiss</Button> : null}
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
