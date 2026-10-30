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
import { STUDY_MASTERY_STATUS_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

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
  const { t } = useTranslation()
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
    return <Card aria-label={t('study.studyProgressPanel.title')}><CardContent className="p-6"><p role="status">{t('study.studyProgressPanel.loading')}</p></CardContent></Card>
  }
  if (effectiveState === 'error') {
    return <Card aria-label={t('study.studyProgressPanel.title')}><CardContent className="space-y-3 p-6"><p role="alert" className="text-sm text-destructive">{t('study.studyProgressPanel.loadError')}</p><Button type="button" variant="outline" onClick={onRetry}>{t('study.studyProgressPanel.retry')}</Button></CardContent></Card>
  }
  if (effectiveState === 'ready' && !decoded) {
    return <Card aria-label={t('study.studyProgressPanel.title')}><CardContent className="space-y-3 p-6"><p role="alert" className="text-sm text-destructive">{t('study.studyProgressPanel.readError')}</p><Button type="button" variant="outline" onClick={onRetry}>{t('study.studyProgressPanel.retry')}</Button></CardContent></Card>
  }
  if (effectiveState === 'empty' || !decoded) {
    return <Card aria-label={t('study.studyProgressPanel.title')}><CardHeader><CardTitle className="text-base">{t('study.studyProgressPanel.title')}</CardTitle></CardHeader><CardContent><p className="text-sm text-muted-foreground">{t('study.studyProgressPanel.empty')}</p></CardContent></Card>
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
    <Card aria-label={t('study.studyProgressPanel.title')}>
      <CardHeader className="border-b pb-4">
        <CardTitle className="text-lg">{t('study.studyProgressPanel.title')}</CardTitle>
        <CardDescription>{t('study.studyProgressPanel.summary', { concepts: decoded.concepts.length, reviews: decoded.review_consistency.reviews, onTime: Math.round(decoded.review_consistency.on_time_rate * 100) })}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        <ul role="list" aria-label={t('study.studyProgressPanel.conceptMastery')} className="space-y-3">
          {decoded.concepts.map((concept) => (
            <li key={concept.concept_id} className="rounded-md border p-3">
              <div className="flex items-center justify-between gap-3"><span className="font-medium">{concept.concept_id}</span><span className="text-xs text-muted-foreground">{enumLabel(t, STUDY_MASTERY_STATUS_KEYS, concept.status, spacedEnum(concept.status))}</span></div>
              <div className="mt-2 h-2 rounded-full bg-muted" aria-label={t('study.studyProgressPanel.masteryAria', { concept: concept.concept_id })}><div className="h-2 rounded-full bg-primary" style={{ width: `${Math.round(concept.score * 100)}%` }} /></div>
              <p className="mt-1 text-xs text-muted-foreground">{concept.attempts === 1 ? t('study.studyProgressPanel.observationsOne', { score: Math.round(concept.score * 100), count: concept.attempts }) : t('study.studyProgressPanel.observationsOther', { score: Math.round(concept.score * 100), count: concept.attempts })}</p>
            </li>
          ))}
        </ul>

        <section aria-labelledby="study-adaptations-heading" className="space-y-3">
          <h3 id="study-adaptations-heading" className="text-sm font-semibold">{t('study.studyProgressPanel.suggestedAdaptations')}</h3>
          {decoded.proposals.length === 0 ? <p className="text-sm text-muted-foreground">{t('study.studyProgressPanel.noAdaptations')}</p> : (
            <ul role="list" className="space-y-3">
              {decoded.proposals.map((proposal) => (
                <li key={proposal.proposal_id} className="rounded-md border p-3">
                  <p className="font-medium">{proposal.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{proposal.rationale}</p>
                  {proposal.available && proposal.status === 'proposed' && (onAccept || onDismiss) ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {onAccept ? <Button type="button" size="sm" className="h-auto min-h-8 max-w-full min-w-0 whitespace-normal text-left" onClick={() => setPending({ proposal, decision: 'accepted', requestId: newDecisionRequestId() })} aria-label={t('study.studyProgressPanel.acceptProposal', { title: proposal.title })}>{t('study.studyProgressPanel.acceptProposal', { title: proposal.title })}</Button> : null}
                      {onDismiss ? <Button type="button" size="sm" variant="outline" className="h-auto min-h-8 max-w-full min-w-0 whitespace-normal text-left" onClick={() => setPending({ proposal, decision: 'dismissed', requestId: newDecisionRequestId() })} aria-label={t('study.studyProgressPanel.dismissProposalAria', { title: proposal.title })}>{t('study.studyProgressPanel.dismiss')}</Button> : null}
                    </div>
                  ) : <p className="mt-3 text-xs text-muted-foreground">{t('study.studyProgressPanel.adaptationUnavailable')}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
      <Dialog open={pending !== null} onOpenChange={(open) => { if (!open && !submitting) setPending(null) }}>
        <DialogContent showCloseButton={!submitting}>
          <DialogHeader>
            <DialogTitle>{pending?.decision === 'accepted' ? t('study.studyProgressPanel.confirmAcceptance') : t('study.studyProgressPanel.confirmDismissal')}</DialogTitle>
            <DialogDescription>{t('study.studyProgressPanel.decisionRecorded', { title: pending?.proposal.title ?? '' })}</DialogDescription>
          </DialogHeader>
          {decisionError ? <p role="alert" className="text-sm text-destructive">{t('study.studyProgressPanel.decisionError')}</p> : null}
          <DialogFooter><Button type="button" onClick={() => void confirm()} disabled={submitting}>{submitting ? t('study.studyProgressPanel.saving') : t('common.confirm')}</Button><Button type="button" variant="outline" onClick={() => setPending(null)} disabled={submitting}>{t('common.cancel')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
