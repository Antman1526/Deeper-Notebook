'use client'

import { Badge } from '@/components/ui/badge'
import type { ResearchEvidence } from '@/lib/api/research'
import { useTranslation } from '@/lib/hooks/use-translation'
import { formatDateTime } from '@/lib/utils/date-locale'

const FINGERPRINT_EDGE_LENGTH = 8

function shortenFingerprint(value: string) {
  const edgeLength = FINGERPRINT_EDGE_LENGTH
  if (value.length <= edgeLength * 2) return value
  return `${value.slice(0, edgeLength)}…${value.slice(-edgeLength)}`
}

function formatRetrievedAt(value: string, language: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return `${formatDateTime(date, language, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  })} UTC`
}

const freshnessLabelKeys: Record<ResearchEvidence['freshness'], string> = {
  fresh: 'research.evidenceReceipt.fresh',
  stale: 'research.evidenceReceipt.stale',
  unknown: 'research.evidenceReceipt.freshnessUnknown',
}

// v0.8.130 — freshness is a status, so it uses the Badge status variants (UI audit Phase 1).
const freshnessVariants: Record<ResearchEvidence['freshness'], 'success' | 'warning' | 'outline'> = {
  fresh: 'success',
  stale: 'warning',
  unknown: 'outline',
}

const freshnessTones: Partial<Record<ResearchEvidence['freshness'], string>> = {
  unknown: 'border-muted-foreground/50 text-muted-foreground',
}

export function EvidenceReceipt({ evidence }: { evidence?: ResearchEvidence | null }) {
  const { t, language } = useTranslation()
  if (!evidence) return null

  const freshnessLabel = t(freshnessLabelKeys[evidence.freshness])

  return (
    <div role="group" aria-label={t('research.evidenceReceipt.receipt')} data-dn-folio-evidence="true" className="mt-2 text-xs">
      <dl className="grid gap-x-3 gap-y-1 @2xl:grid-cols-[auto_1fr]">
        <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.provider')}</dt>
        <dd>{evidence.provider}</dd>

        <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.freshness')}</dt>
        <dd>
          <Badge variant={freshnessVariants[evidence.freshness]} className={freshnessTones[evidence.freshness]} aria-label={t('research.evidenceReceipt.freshnessAria', { label: freshnessLabel })}>
            {freshnessLabel}
          </Badge>
        </dd>

        {evidence.degraded ? (
          <>
            <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.providerPath')}</dt>
            <dd>
              <Badge variant="warning">
                {t('research.evidenceReceipt.fallbackProvider')}
              </Badge>
            </dd>
          </>
        ) : null}

        <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.retrieved')}</dt>
        <dd>
          <time dateTime={evidence.retrieved_at}>{formatRetrievedAt(evidence.retrieved_at, language)}</time>
        </dd>

        <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.sourceFingerprint')}</dt>
        <dd>
          <code
            className="font-mono"
            aria-label={t('research.evidenceReceipt.sourceFingerprintAria', { value: evidence.source_fingerprint })}
            title={evidence.source_fingerprint}
          >
            {shortenFingerprint(evidence.source_fingerprint)}
          </code>
        </dd>

        <dt className="font-medium text-muted-foreground">{t('research.evidenceReceipt.evidenceFingerprint')}</dt>
        <dd>
          <code
            className="font-mono"
            aria-label={t('research.evidenceReceipt.evidenceFingerprintAria', { value: evidence.evidence_id })}
            title={evidence.evidence_id}
          >
            {shortenFingerprint(evidence.evidence_id)}
          </code>
        </dd>
      </dl>
    </div>
  )
}
