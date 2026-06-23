import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { SourceListResponse } from '@/lib/types/api'

export type SourceReadiness = {
  label: string
  className: string
  blocksGeneration: boolean
}

export function getSourceReadiness(source: SourceListResponse): SourceReadiness {
  if (source.status === 'failed') {
    return {
      label: 'Failed',
      className: 'border-destructive text-destructive',
      blocksGeneration: true,
    }
  }

  if (source.status === 'new' || source.status === 'queued' || source.status === 'running') {
    return {
      label: source.status === 'queued' ? 'Queued' : 'Processing',
      className: 'border-[var(--onp-info)] text-[var(--onp-info)]',
      blocksGeneration: true,
    }
  }

  if (!source.embedded) {
    return {
      label: 'Not embedded',
      className: 'border-[var(--onp-warning)] text-[var(--onp-warning)]',
      blocksGeneration: true,
    }
  }

  if (source.extraction_quality === 'no_text') {
    return {
      label: 'No text',
      className: 'border-destructive text-destructive',
      blocksGeneration: true,
    }
  }

  if (source.extraction_quality === 'low_text') {
    return {
      label: 'Low text',
      className: 'border-[var(--onp-warning)] text-[var(--onp-warning)]',
      blocksGeneration: false,
    }
  }

  return {
    label: 'Ready',
    className: 'border-[var(--onp-success)] text-[var(--onp-success)]',
    blocksGeneration: false,
  }
}

export function SourceHealthPill({ source }: { source: SourceListResponse }) {
  const readiness = getSourceReadiness(source)

  return (
    <Badge
      variant="outline"
      className={cn('text-[0.68rem]', readiness.className)}
    >
      {readiness.label}
    </Badge>
  )
}
