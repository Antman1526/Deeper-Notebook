'use client'

import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import type { SourceListResponse } from '@/lib/types/api'

export type SourceReadiness = {
  labelKey: string
  className: string
  blocksGeneration: boolean
}

export function getSourceReadiness(source: SourceListResponse): SourceReadiness {
  if (source.status === 'failed') {
    return {
      labelKey: 'workspace.sourceHealthPill.failed',
      className: 'border-destructive text-destructive',
      blocksGeneration: true,
    }
  }

  if (source.status === 'new' || source.status === 'queued' || source.status === 'running') {
    return {
      labelKey: source.status === 'queued' ? 'workspace.sourceHealthPill.queued' : 'workspace.sourceHealthPill.processing',
      className: 'border-[var(--dn-info)] text-[var(--dn-info)]',
      blocksGeneration: true,
    }
  }

  if (!source.embedded) {
    return {
      labelKey: 'workspace.sourceHealthPill.notEmbedded',
      className: 'border-[var(--dn-warning)] text-[var(--dn-warning)]',
      blocksGeneration: true,
    }
  }

  if (source.extraction_quality === 'no_text') {
    return {
      labelKey: 'workspace.sourceHealthPill.noText',
      className: 'border-destructive text-destructive',
      blocksGeneration: true,
    }
  }

  if (source.extraction_quality === 'low_text') {
    return {
      labelKey: 'workspace.sourceHealthPill.lowText',
      className: 'border-[var(--dn-warning)] text-[var(--dn-warning)]',
      blocksGeneration: false,
    }
  }

  return {
    labelKey: 'workspace.sourceHealthPill.ready',
    className: 'border-[var(--dn-success)] text-[var(--dn-success)]',
    blocksGeneration: false,
  }
}

export function SourceHealthPill({ source }: { source: SourceListResponse }) {
  const { t } = useTranslation()
  const readiness = getSourceReadiness(source)

  return (
    <Badge
      variant="outline"
      // v0.8.130 — 12px type floor (UI audit Phase 1)
      className={cn('text-xs', readiness.className)}
    >
      {t(readiness.labelKey)}
    </Badge>
  )
}
