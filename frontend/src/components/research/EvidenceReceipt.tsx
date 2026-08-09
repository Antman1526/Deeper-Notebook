'use client'

import { Badge } from '@/components/ui/badge'
import type { ResearchEvidence } from '@/lib/api/research'

const FINGERPRINT_EDGE_LENGTH = 8

function shortenFingerprint(value: string) {
  const edgeLength = FINGERPRINT_EDGE_LENGTH
  if (value.length <= edgeLength * 2) return value
  return `${value.slice(0, edgeLength)}…${value.slice(-edgeLength)}`
}

function formatRetrievedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return `${new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date)} UTC`
}

const freshnessLabels: Record<ResearchEvidence['freshness'], string> = {
  fresh: 'Fresh',
  stale: 'Stale',
  unknown: 'Freshness unknown',
}

const freshnessTones: Record<ResearchEvidence['freshness'], string> = {
  fresh: 'border-emerald-600/60 text-emerald-700 dark:text-emerald-400',
  stale: 'border-amber-500/70 text-amber-700 dark:text-amber-400',
  unknown: 'border-muted-foreground/50 text-muted-foreground',
}

export function EvidenceReceipt({ evidence }: { evidence?: ResearchEvidence | null }) {
  if (!evidence) return null

  const freshnessLabel = freshnessLabels[evidence.freshness]

  return (
    <div role="group" aria-label="Evidence receipt" className="mt-2 rounded-md border bg-muted/30 p-2 text-xs">
      <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[auto_1fr]">
        <dt className="font-medium text-muted-foreground">Provider</dt>
        <dd>{evidence.provider}</dd>

        <dt className="font-medium text-muted-foreground">Freshness</dt>
        <dd>
          <Badge variant="outline" className={freshnessTones[evidence.freshness]} aria-label={`Freshness: ${freshnessLabel}`}>
            {freshnessLabel}
          </Badge>
        </dd>

        {evidence.degraded ? (
          <>
            <dt className="font-medium text-muted-foreground">Provider path</dt>
            <dd>
              <Badge variant="outline" className="border-amber-500/70 text-amber-700 dark:text-amber-400">
                Fallback provider
              </Badge>
            </dd>
          </>
        ) : null}

        <dt className="font-medium text-muted-foreground">Retrieved</dt>
        <dd>
          <time dateTime={evidence.retrieved_at}>{formatRetrievedAt(evidence.retrieved_at)}</time>
        </dd>

        <dt className="font-medium text-muted-foreground">Source fingerprint</dt>
        <dd>
          <code
            className="font-mono"
            aria-label={`Source fingerprint: ${evidence.source_fingerprint}`}
            title={evidence.source_fingerprint}
          >
            {shortenFingerprint(evidence.source_fingerprint)}
          </code>
        </dd>

        <dt className="font-medium text-muted-foreground">Evidence fingerprint</dt>
        <dd>
          <code
            className="font-mono"
            aria-label={`Evidence fingerprint: ${evidence.evidence_id}`}
            title={evidence.evidence_id}
          >
            {shortenFingerprint(evidence.evidence_id)}
          </code>
        </dd>
      </dl>
    </div>
  )
}
