'use client'

import { AlertTriangle, ExternalLink, Quote } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { ClaimVerdict } from '@/lib/api/evaluations'
import { useTranslation } from '@/lib/hooks/use-translation'

const LABEL_KEYS: Record<ClaimVerdict['status'], string> = {
  supported: 'evaluation.claimReviewDrawer.supported',
  partial: 'evaluation.claimReviewDrawer.partial',
  contradicted: 'evaluation.claimReviewDrawer.contradicted',
  unsupported: 'evaluation.claimReviewDrawer.unsupported',
  uncited: 'evaluation.claimReviewDrawer.uncited',
}

export function ClaimReviewDrawer({
  open,
  onOpenChange,
  verdicts,
  status = 'completed',
  error,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  verdicts: ClaimVerdict[]
  status?: 'pending' | 'running' | 'completed' | 'failed'
  error?: string | null
}) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto p-5">
        <DialogHeader>
          <DialogTitle>{t('evaluation.claimReviewDrawer.title')}</DialogTitle>
          <DialogDescription>{t('evaluation.claimReviewDrawer.description')}</DialogDescription>
        </DialogHeader>
        {status === 'pending' || status === 'running' ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t('evaluation.claimReviewDrawer.running')}
          </p>
        ) : status === 'failed' ? (
          <p role="status" className="text-sm text-muted-foreground">
            {error || t('evaluation.claimReviewDrawer.failed')}
          </p>
        ) : verdicts.length === 0 ? (
          <p role="status" className="text-sm text-muted-foreground">
            {t('evaluation.claimReviewDrawer.noClaims')}
          </p>
        ) : (
          <div className="space-y-3">
            {verdicts.map((verdict, index) => {
              const critical = verdict.status === 'contradicted' || verdict.status === 'unsupported'
              return (
                <article key={`${verdict.claim}-${index}`} className={critical ? 'border-destructive/60 rounded-md border p-3' : 'rounded-md border p-3'}>
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium leading-6">{verdict.claim}</p>
                    <Badge variant={critical ? 'destructive' : 'outline'}>{critical && <AlertTriangle aria-hidden="true" />}{t(LABEL_KEYS[verdict.status])}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{verdict.explanation}</p>
                  {verdict.evidence.map((evidence, evidenceIndex) => (
                    <section key={`${evidence.source_id}-${evidence.start}-${evidenceIndex}`} className="mt-3 border-l-2 border-primary/60 pl-3">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground"><Quote className="size-3" aria-hidden="true" />{evidence.source_state === 'source_changed' ? t('evaluation.claimReviewDrawer.sourceChanged') : t('evaluation.claimReviewDrawer.exactEvidence')}</div>
                      <blockquote className="mt-1 text-sm leading-6">{evidence.quote}</blockquote>
                      <Button asChild variant="link" size="sm" className="mt-1 h-auto px-0"><a href={`/sources/${encodeURIComponent(evidence.source_id)}`}><ExternalLink aria-hidden="true" />{t('evaluation.claimReviewDrawer.openSource')}</a></Button>
                    </section>
                  ))}
                </article>
              )
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
