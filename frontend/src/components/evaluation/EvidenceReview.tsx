'use client'

import { useMemo, useState } from 'react'

import { ClaimReviewDrawer } from './ClaimReviewDrawer'
import { EvidenceQualityBadge } from './EvidenceQualityBadge'
import { useLatestEvaluation } from '@/lib/hooks/use-evaluation'
import type { EvaluationDetail } from '@/lib/api/evaluations'
import { useTranslation } from '@/lib/hooks/use-translation'

export function EvidenceReview({
  notebookId,
  artifactId,
  messageId,
  className,
  evaluation,
  batchLoading = false,
  batchError = false,
}: {
  notebookId: string
  artifactId?: string | null
  messageId?: string | null
  className?: string
  /** When supplied, the caller owns a shared batch request. */
  evaluation?: EvaluationDetail | null
  batchLoading?: boolean
  batchError?: boolean
}) {
  const { t } = useTranslation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const selector = useMemo(() => {
    if (artifactId && !messageId) return { artifactId }
    if (messageId && !artifactId) return { messageId }
    return undefined
  }, [artifactId, messageId])
  const delegatedToBatch = evaluation !== undefined || batchLoading || batchError
  const latestQuery = useLatestEvaluation(
    delegatedToBatch ? undefined : notebookId,
    delegatedToBatch ? undefined : selector,
  )
  const data = delegatedToBatch ? evaluation : latestQuery.data

  if (!selector) {
    return (
      <span className={className} role="status" data-testid="evidence-review">
        {t('evaluation.evidenceReview.unavailable')}
      </span>
    )
  }
  if (batchLoading || latestQuery.isLoading) {
    return (
      <span className={className} role="status" data-testid="evidence-review">
        {t('evaluation.evidenceReview.checking')}
      </span>
    )
  }
  if (batchError || latestQuery.isError) {
    return (
      <span className={className} role="status" data-testid="evidence-review">
        {t('evaluation.evidenceReview.unavailable')}
      </span>
    )
  }
  if (!data) {
    return (
      <span className={className} role="status" data-testid="evidence-review">
        {t('evaluation.evidenceReview.none')}
      </span>
    )
  }

  return (
    <span className={className} data-testid="evidence-review">
      <EvidenceQualityBadge
        counts={data.counts}
        status={data.status}
        onClick={() => setDrawerOpen(true)}
      />
      <ClaimReviewDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        verdicts={data.verdicts}
        status={data.status}
        error={data.run.error}
      />
    </span>
  )
}
