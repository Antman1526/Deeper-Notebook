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
  const tone = critical > 0
    ? 'border-destructive/70 text-destructive'
    : uncertain > 0 || status === 'failed'
      ? 'border-amber-500/70 text-amber-700 dark:text-amber-400'
      : 'border-emerald-600/60 text-emerald-700 dark:text-emerald-400'

  return (
    <Badge
      variant="outline"
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onClick()
        }
      }}
      className={cn('cursor-default text-[0.68rem]', onClick && 'cursor-pointer', tone)}
      aria-label={label}
    >
      <Icon aria-hidden="true" />
      {label}
    </Badge>
  )
}
