'use client'

import type { ReactNode } from 'react'
import { FilePenLine, LockKeyhole } from 'lucide-react'

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

function redactModelPaths(value: string): string {
  return value
    .replace(/(^|\s)\/(?:[^\n]*)/g, '$1[local path redacted]')
    .replace(/(^|\s)[A-Za-z]:\\(?:[^\n]*)/g, '$1[local path redacted]')
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
  const readinessDetail = redactModelPaths(readiness.detail)
  const readinessLabel = {
    ready: 'Local readiness: ready',
    loading: 'Local readiness: loading',
    unavailable: 'Local readiness: unavailable',
  }[readiness.state]
  return (
    <header role="group" aria-label="Research Core workspace" className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-b border-border/70 bg-card/60 px-5 py-3.5 transition-colors">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">{workspaceTitle}</h1>
        <div className="research-core-authority mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground" role="group" aria-label="Source authority summary">
          {/* v0.8.130 — authority chips from theme tokens: brand tint for app-owned, warning for read-only (UI audit Phase 1) */}
          <span data-authority="app-owned" className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 font-medium text-primary">
            <FilePenLine className="h-3.5 w-3.5" aria-hidden="true" />
            {authoritySummary.appOwned} app-owned editable
          </span>
          <span data-authority="external-read-only" className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning-soft px-2.5 py-0.5 font-medium text-warning-ink">
            <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />
            {authoritySummary.externalReadOnly} external read-only
          </span>
        </div>
      </div>
      <dl className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">Save state</dt>
          <dd>{saveState}</dd>
        </div>
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">Memory pressure</dt>
          <dd data-state={memoryPressure.state}>{memoryPressure.detail}</dd>
        </div>
        <div className="rounded-lg border border-border/60 bg-background/50 px-2.5 py-1 text-muted-foreground shadow-sm">
          <dt className="sr-only">Queued work</dt>
          <dd>{queuedWorkCount} queued</dd>
        </div>
      </dl>
      {actions ? <div className="shrink-0">{actions}</div> : null}
      <details className="basis-full text-xs text-muted-foreground">
        <summary
          role="button"
          aria-label={`${readinessLabel} — ${readinessDetail}`}
          className="cursor-pointer select-none rounded-lg border border-border/50 bg-background/40 px-3 py-1.5 font-medium hover:bg-accent/50 hover:text-foreground transition-colors"
        >
          {readinessLabel} — {readinessDetail}
        </summary>
        {readiness.models?.length ? (
          <ul className="mt-2 flex flex-wrap gap-2 pt-1" aria-label="Local readiness details">
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
