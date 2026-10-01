'use client'

import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { EvidenceStatus } from '@/lib/api/evaluations'

type Counts = Partial<Record<EvidenceStatus, number>>

export function EvidenceQualityBadge({
  counts,
  status = 'completed',
  onClick,
}: {
  counts: Counts
  status?: 'pending' | 'running' | 'completed' | 'failed'
  onClick?: () => void
}) {
  const critical = (counts.contradicted ?? 0) + (counts.unsupported ?? 0)
  const uncertain = (counts.partial ?? 0) + (counts.uncited ?? 0)
  const total = Object.values(counts).reduce((sum, count) => sum + (count ?? 0), 0)
  const label =
    status === 'pending' || status === 'running'
      ? 'Checking evidence'
      : status === 'failed'
      ? 'Evidence review failed'
      : total === 0
        ? 'No claims reviewed'
        : critical > 0
          ? `${critical} evidence issue${critical === 1 ? '' : 's'}`
          : uncertain > 0
            ? `${uncertain} claim${uncertain === 1 ? '' : 's'} need review`
            : 'Evidence supported'
  const Icon = critical > 0 ? ShieldAlert : uncertain > 0 || status === 'failed' ? ShieldQuestion : ShieldCheck
  // v0.8.130 — status colours from theme tokens (UI audit Phase 1): the warning
  // and success states are Badge variants; the critical state uses the same soft
  // destructive tint so all three read as one family.
  // v0.8.130 — "Checking evidence" was a green success pill before anything had
  // been checked; in-flight is info and "No claims reviewed" is neutral.
  const variant = critical > 0
    ? 'outline'
    : uncertain > 0 || status === 'failed'
      ? 'warning'
      : status === 'pending' || status === 'running'
        ? 'info'
        : total === 0
          ? 'outline'
          : 'success'
  const tone = critical > 0 ? 'border-transparent bg-destructive-soft text-destructive-ink' : undefined

  return (
    <Badge
      variant={variant}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onClick()
        }
      }}
      className={cn('cursor-default text-xs', onClick && 'cursor-pointer', tone)}
      aria-label={label}
    >
      <Icon aria-hidden="true" />
      {label}
    </Badge>
  )
}
