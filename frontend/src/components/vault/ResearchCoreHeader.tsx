'use client'

import type { ReactNode } from 'react'
import { FilePenLine, LockKeyhole } from 'lucide-react'

import { useTranslation } from '@/lib/hooks/use-translation'

export interface ResearchCoreReadiness {
  state: 'ready' | 'loading' | 'unavailable'
  detail: string
  models?: Array<{ id: string; provider: string; path?: string }>
}

interface ResearchCoreHeaderProps {
  workspaceTitle: string
  authoritySummary: { appOwned: number; externalReadOnly: number }
  saveState: string
  readiness: ResearchCoreReadiness
  memoryPressure: { state: 'normal' | 'elevated' | 'high'; detail: string }
  queuedWorkCount: number
  actions?: ReactNode
}

function redactModelPaths(value: string, replacement: string): string {
  return value
    .replace(/(^|\s)\/(?:[^\n]*)/g, `$1${replacement}`)
    .replace(/(^|\s)[A-Za-z]:\\(?:[^\n]*)/g, `$1${replacement}`)
}

export function ResearchCoreHeader({
  workspaceTitle,
  authoritySummary,
  saveState,
  readiness,
  memoryPressure,
  queuedWorkCount,
  actions,
}: ResearchCoreHeaderProps) {
  const { t } = useTranslation()
  const readinessDetail = redactModelPaths(readiness.detail, t('knowledge.researchCoreHeader.pathRedacted'))
  const readinessSummary = {
    ready: t('knowledge.researchCoreHeader.readinessReady', { detail: readinessDetail }),
    loading: t('knowledge.researchCoreHeader.readinessLoading', { detail: readinessDetail }),
    unavailable: t('knowledge.researchCoreHeader.readinessUnavailable', { detail: readinessDetail }),
  }[readiness.state]
  return (
    <header role="group" aria-label={t('knowledge.researchCoreHeader.workspace')} className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-b border-border/70 bg-card/60 px-5 py-3.5 transition-colors">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">{workspaceTitle}</h1>
        <div className="research-core-authority mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground" role="group" aria-label={t('knowledge.researchCoreHeader.authoritySummary')}>
          {/* v0.8.130 — authority chips from theme tokens: brand tint for app-owned, warning for read-only (UI audit Phase 1) */}
          <span data-authority="app-owned" className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 font-medium text-primary">
            <FilePenLine className="h-3.5 w-3.5" aria-hidden="true" />
            {t('knowledge.researchCoreHeader.appOwnedEditable', { count: authoritySummary.appOwned })}
          </span>
          <span data-authority="external-read-only" className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 font-medium text-warning-ink">
            <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />
            {t('knowledge.researchCoreHeader.externalReadOnly', { count: authoritySummary.externalReadOnly })}
          </span>
        </div>
      </div>
      <dl className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">{t('knowledge.researchCoreHeader.saveState')}</dt>
          <dd>{saveState}</dd>
        </div>
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">{t('knowledge.researchCoreHeader.memoryPressure')}</dt>
          <dd data-state={memoryPressure.state}>{memoryPressure.detail}</dd>
        </div>
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">{t('knowledge.researchCoreHeader.queuedWork')}</dt>
          <dd>{t('knowledge.researchCoreHeader.queued', { count: queuedWorkCount })}</dd>
        </div>
      </dl>
      {actions ? <div className="shrink-0">{actions}</div> : null}
      <details className="basis-full text-xs text-muted-foreground">
        <summary
          role="button"
          aria-label={readinessSummary}
          className="cursor-pointer select-none rounded-lg border border-border/50 bg-background/40 px-3 py-1.5 font-medium hover:bg-accent/50 hover:text-foreground transition-colors"
        >
          {readinessSummary}
        </summary>
        {readiness.models?.length ? (
          <ul className="mt-2 flex flex-wrap gap-2 pt-1" aria-label={t('knowledge.researchCoreHeader.readinessDetails')}>
            {readiness.models.map((model) => (
              <li key={`${model.provider}:${model.id}`} className="rounded-md border border-border/40 bg-muted/30 px-2 py-0.5 text-xs">
                {model.id} · {model.provider}
              </li>
            ))}
          </ul>
        ) : null}
      </details>
    </header>
  )
}
